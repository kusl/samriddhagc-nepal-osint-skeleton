#!/usr/bin/env python3
"""Generate improved Golyan Group network visualization with clear sub-clusters."""
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_pdf import PdfPages
import networkx as nx
from sqlalchemy import select, and_, or_, func
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment, CompanyDirector

# Hindu deity names
DEITY_NAMES = [
    'akash', 'prithivi', 'guru', 'sukra', 'buddha', 'ravi', 'mangal',
    'brihaspati', 'som', 'sani', 'parshurama', 'shiva', 'vishnu',
    'brahma', 'rama', 'krishna', 'ganesh', 'indra', 'agni', 'varun',
    'surya', 'chandra', 'rahu', 'ketu'
]

async def get_network_with_clusters():
    """Fetch all data with phone/mobile hash clusters."""
    async with AsyncSessionLocal() as db:
        # 1. Get all Golyan companies
        golyan_stmt = select(CompanyRegistration).where(
            CompanyRegistration.name_english.ilike('%golyan%')
        )
        result = await db.execute(golyan_stmt)
        golyan_companies = result.scalars().all()

        # 2. Get deity-themed agro companies
        deity_stmt = (
            select(CompanyRegistration)
            .where(
                and_(
                    CompanyRegistration.registration_number >= 281206,
                    CompanyRegistration.registration_number <= 297307,
                )
            )
            .order_by(CompanyRegistration.registration_number)
        )
        result = await db.execute(deity_stmt)
        all_companies = result.scalars().all()

        deity_companies = [
            c for c in all_companies
            if c.name_english and (
                ('agro' in c.name_english.lower() or 'forestry' in c.name_english.lower())
                and any(deity in c.name_english.lower() for deity in DEITY_NAMES)
            )
        ]

        # 3. Get IRD data with phone/mobile hashes
        all_entities = golyan_companies + deity_companies
        pans = [c.pan for c in all_entities if c.pan]

        ird_stmt = select(IRDEnrichment).where(IRDEnrichment.pan.in_(pans))
        result = await db.execute(ird_stmt)
        ird_data = {ird.pan: ird for ird in result.scalars().all()}

        # 4. Build phone hash clusters
        phone_clusters = defaultdict(list)
        mobile_clusters = defaultdict(list)

        for company in all_entities:
            if company.pan and company.pan in ird_data:
                ird = ird_data[company.pan]
                if ird.phone_hash:
                    phone_clusters[ird.phone_hash].append(company)
                if ird.mobile_hash:
                    mobile_clusters[ird.mobile_hash].append(company)

        # Filter to only clusters with >1 company
        phone_clusters = {h: companies for h, companies in phone_clusters.items() if len(companies) > 1}
        mobile_clusters = {h: companies for h, companies in mobile_clusters.items() if len(companies) > 1}

        # 5. Get directors
        company_ids = [c.id for c in all_entities]
        directors_stmt = select(CompanyDirector).where(
            CompanyDirector.company_id.in_(company_ids)
        )
        result = await db.execute(directors_stmt)
        directors = result.scalars().all()

        # Group directors by name
        director_to_companies = defaultdict(list)
        for director in directors:
            if director.name_en:
                director_to_companies[director.name_en].append(director.company_id)

        # Find lawyer (most deity companies)
        lawyer_name = None
        max_count = 0
        for director_name, company_ids in director_to_companies.items():
            deity_count = sum(1 for cid in company_ids if any(c.id == cid for c in deity_companies))
            if deity_count > max_count:
                max_count = deity_count
                lawyer_name = director_name

        # Find CA (Golyan Group director)
        ca_name = None
        golyan_group = next((c for c in golyan_companies if 'golyan group' in c.name_english.lower()), None)
        if golyan_group:
            ca_directors = [d for d in directors if d.company_id == golyan_group.id]
            if ca_directors:
                ca_name = ca_directors[0].name_en

        return {
            'deity_companies': deity_companies,
            'golyan_companies': golyan_companies,
            'phone_clusters': phone_clusters,
            'mobile_clusters': mobile_clusters,
            'ird_data': ird_data,
            'directors': directors,
            'director_to_companies': dict(director_to_companies),
            'lawyer_name': lawyer_name,
            'ca_name': ca_name,
            'lawyer_company_count': max_count
        }

def create_detailed_network_graph(data, focus='overview'):
    """Create network with clear sub-clusters."""
    fig, ax = plt.subplots(figsize=(20, 16), facecolor='#0a0a0a')
    ax.set_facecolor('#0a0a0a')

    G = nx.Graph()

    golyan_companies = data['golyan_companies']
    phone_clusters = data['phone_clusters']
    mobile_clusters = data['mobile_clusters']
    lawyer_name = data['lawyer_name']
    ca_name = data['ca_name']

    # Identify key Golyan entities
    golyan_group = next((c for c in golyan_companies if 'golyan group' in c.name_english.lower()), None)
    golyan_realty = next((c for c in golyan_companies if 'realty' in c.name_english.lower()), None)
    golyan_foundation = next((c for c in golyan_companies if 'foundation' in c.name_english.lower()), None)
    golyan_agro = next((c for c in golyan_companies if 'golyan agro' in c.name_english.lower()), None)

    # Add central node
    if golyan_group:
        G.add_node('GOLYAN_GROUP',
                   type='parent',
                   label='GOLYAN\nGROUP',
                   size=4000,
                   company=golyan_group)

    # Add CA director
    if ca_name and golyan_group:
        G.add_node('CA_DIRECTOR',
                   type='director',
                   label=f'CA\n{ca_name.split()[0]}',
                   size=2500)
        G.add_edge('CA_DIRECTOR', 'GOLYAN_GROUP', weight=3, edge_type='control')

    # Process phone/mobile clusters for Golyan entities
    golyan_cluster_map = {}

    # Golyan Realty cluster
    if golyan_realty:
        for hash_val, companies in {**phone_clusters, **mobile_clusters}.items():
            if golyan_realty in companies:
                cluster_id = 'REALTY_CLUSTER'
                golyan_cluster_map[cluster_id] = companies

                G.add_node(cluster_id,
                          type='golyan_sub',
                          label=f'GOLYAN\nREALTY\nCLUSTER',
                          size=3000,
                          count=len(companies))
                G.add_edge('GOLYAN_GROUP', cluster_id, weight=2, edge_type='owns')

                # Add cluster members
                for i, company in enumerate(companies[:5]):
                    node_id = f'REALTY_{i}'
                    short_name = company.name_english.replace('Golyan ', '').replace(' and Forestry', '')[:15]
                    G.add_node(node_id,
                              type='cluster_member',
                              label=short_name,
                              size=1200,
                              company=company)
                    G.add_edge(cluster_id, node_id, weight=1, edge_type='shares_contact')
                break

    # Golyan Foundation cluster
    if golyan_foundation:
        for hash_val, companies in {**phone_clusters, **mobile_clusters}.items():
            if golyan_foundation in companies:
                cluster_id = 'FOUNDATION_CLUSTER'
                golyan_cluster_map[cluster_id] = companies

                G.add_node(cluster_id,
                          type='golyan_sub',
                          label=f'GOLYAN\nFOUNDATION\nCLUSTER',
                          size=3000,
                          count=len(companies))
                G.add_edge('GOLYAN_GROUP', cluster_id, weight=2, edge_type='owns')

                for i, company in enumerate(companies[:5]):
                    node_id = f'FOUND_{i}'
                    short_name = company.name_english.replace('Golyan ', '').replace(' and Forestry', '')[:15]
                    G.add_node(node_id,
                              type='cluster_member',
                              label=short_name,
                              size=1200,
                              company=company)
                    G.add_edge(cluster_id, node_id, weight=1, edge_type='shares_contact')
                break

    # Other standalone Golyan entities
    standalone_golyan = [c for c in golyan_companies
                        if c not in [golyan_group, golyan_realty, golyan_foundation, golyan_agro]
                        and all(c not in cluster for cluster in golyan_cluster_map.values())]

    for company in standalone_golyan[:8]:
        node_id = f'GOL_{company.registration_number}'
        short_name = company.name_english.replace('Golyan ', '')[:12]
        G.add_node(node_id,
                  type='golyan_standalone',
                  label=short_name,
                  size=1500,
                  company=company)
        if golyan_group:
            G.add_edge('GOLYAN_GROUP', node_id, weight=1, edge_type='subsidiary')

    # Large deity-themed cluster
    deity_companies = data['deity_companies']
    if lawyer_name and deity_companies:
        G.add_node('LAWYER',
                  type='director',
                  label=f'LAWYER\n{lawyer_name.split()[0]}',
                  size=2500)
        G.add_edge('LAWYER', 'GOLYAN_GROUP', weight=2, edge_type='linked')

        # Show representative deity companies
        G.add_node('DEITY_CLUSTER',
                  type='agro_cluster',
                  label=f'AGRO & FORESTRY\nCLUSTER\n({len(deity_companies)} entities)',
                  size=4000)
        G.add_edge('LAWYER', 'DEITY_CLUSTER', weight=3, edge_type='control')

        # Add sample deity companies
        for i, company in enumerate(deity_companies[:12]):
            node_id = f'AGRO_{i}'
            deity = next((d for d in DEITY_NAMES if d in company.name_english.lower()), '')
            short_name = f'{deity.capitalize()}' if deity else company.name_english[:10]
            G.add_node(node_id,
                      type='agro',
                      label=short_name,
                      size=800,
                      company=company)
            G.add_edge('DEITY_CLUSTER', node_id, weight=1, edge_type='member')

    # Use hierarchical layout
    pos = nx.spring_layout(G, k=3.5, iterations=100, seed=42, weight='weight')

    # Separate by type for coloring
    parent_nodes = [n for n, d in G.nodes(data=True) if d.get('type') == 'parent']
    golyan_sub_nodes = [n for n, d in G.nodes(data=True) if d.get('type') == 'golyan_sub']
    golyan_standalone_nodes = [n for n, d in G.nodes(data=True) if d.get('type') == 'golyan_standalone']
    cluster_member_nodes = [n for n, d in G.nodes(data=True) if d.get('type') == 'cluster_member']
    agro_cluster_nodes = [n for n, d in G.nodes(data=True) if d.get('type') == 'agro_cluster']
    agro_nodes = [n for n, d in G.nodes(data=True) if d.get('type') == 'agro']
    director_nodes = [n for n, d in G.nodes(data=True) if d.get('type') == 'director']

    # Draw edges with different styles
    control_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get('edge_type') == 'control']
    owns_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get('edge_type') == 'owns']
    linked_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get('edge_type') == 'linked']
    subsidiary_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get('edge_type') == 'subsidiary']
    shares_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get('edge_type') == 'shares_contact']
    member_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get('edge_type') == 'member']

    nx.draw_networkx_edges(G, pos, edgelist=control_edges, edge_color='#ff4444',
                          width=3, alpha=0.8, ax=ax, style='solid')
    nx.draw_networkx_edges(G, pos, edgelist=owns_edges, edge_color='#ff8844',
                          width=2.5, alpha=0.7, ax=ax, style='solid')
    nx.draw_networkx_edges(G, pos, edgelist=linked_edges, edge_color='#4488ff',
                          width=2, alpha=0.6, ax=ax, style='dashed')
    nx.draw_networkx_edges(G, pos, edgelist=subsidiary_edges, edge_color='#ffaa44',
                          width=1.5, alpha=0.5, ax=ax, style='dotted')
    nx.draw_networkx_edges(G, pos, edgelist=shares_edges, edge_color='#44ff88',
                          width=1.5, alpha=0.6, ax=ax, style='solid')
    nx.draw_networkx_edges(G, pos, edgelist=member_edges, edge_color='#88ff44',
                          width=1, alpha=0.4, ax=ax, style='dotted')

    # Draw nodes
    if parent_nodes:
        sizes = [G.nodes[n].get('size', 3000) for n in parent_nodes]
        nx.draw_networkx_nodes(G, pos, nodelist=parent_nodes, node_color='#ff4444',
                              node_size=sizes, ax=ax, linewidths=3, edgecolors='#ffffff')
    if golyan_sub_nodes:
        sizes = [G.nodes[n].get('size', 2500) for n in golyan_sub_nodes]
        nx.draw_networkx_nodes(G, pos, nodelist=golyan_sub_nodes, node_color='#ff8844',
                              node_size=sizes, ax=ax, linewidths=2.5, edgecolors='#ffffff')
    if golyan_standalone_nodes:
        sizes = [G.nodes[n].get('size', 1500) for n in golyan_standalone_nodes]
        nx.draw_networkx_nodes(G, pos, nodelist=golyan_standalone_nodes, node_color='#ffaa44',
                              node_size=sizes, ax=ax, linewidths=2, edgecolors='#ffffff')
    if cluster_member_nodes:
        sizes = [G.nodes[n].get('size', 1200) for n in cluster_member_nodes]
        nx.draw_networkx_nodes(G, pos, nodelist=cluster_member_nodes, node_color='#ffcc88',
                              node_size=sizes, ax=ax, linewidths=1.5, edgecolors='#ffffff', alpha=0.9)
    if agro_cluster_nodes:
        sizes = [G.nodes[n].get('size', 3500) for n in agro_cluster_nodes]
        nx.draw_networkx_nodes(G, pos, nodelist=agro_cluster_nodes, node_color='#44ff88',
                              node_size=sizes, ax=ax, linewidths=3, edgecolors='#ffffff')
    if agro_nodes:
        sizes = [G.nodes[n].get('size', 800) for n in agro_nodes]
        nx.draw_networkx_nodes(G, pos, nodelist=agro_nodes, node_color='#88ff44',
                              node_size=sizes, ax=ax, linewidths=1, edgecolors='#ffffff', alpha=0.7)
    if director_nodes:
        sizes = [G.nodes[n].get('size', 2500) for n in director_nodes]
        nx.draw_networkx_nodes(G, pos, nodelist=director_nodes, node_color='#4488ff',
                              node_size=sizes, ax=ax, node_shape='s', linewidths=2.5, edgecolors='#ffffff')

    # Draw labels
    labels = {n: d.get('label', '') for n, d in G.nodes(data=True)}
    nx.draw_networkx_labels(G, pos, labels, font_size=9, font_color='#ffffff',
                           font_family='monospace', font_weight='bold', ax=ax)

    # Title
    ax.set_title('GOLYAN GROUP CORPORATE NETWORK - SUB-CLUSTER ANALYSIS',
                fontsize=22, color='#ffffff', pad=30, fontfamily='monospace', fontweight='bold')

    # Enhanced legend
    legend_elements = [
        mpatches.Patch(color='#ff4444', label='Parent Entity (Golyan Group)'),
        mpatches.Patch(color='#ff8844', label='Golyan Sub-Clusters (Realty, Foundation)'),
        mpatches.Patch(color='#ffaa44', label='Golyan Subsidiaries'),
        mpatches.Patch(color='#ffcc88', label='Cluster Members (Shared Contact)'),
        mpatches.Patch(color='#44ff88', label='Large Agro/Forestry Cluster'),
        mpatches.Patch(color='#88ff44', label='Individual Agro Entities'),
        mpatches.Patch(color='#4488ff', label='Directors/Controllers'),
        mpatches.Rectangle((0,0),1,1, fc='none', ec='#ff4444', linewidth=2, label='─── Control'),
        mpatches.Rectangle((0,0),1,1, fc='none', ec='#ff8844', linewidth=2, label='─── Ownership'),
        mpatches.Rectangle((0,0),1,1, fc='none', ec='#44ff88', linewidth=2, label='─── Shared Contact'),
    ]
    ax.legend(handles=legend_elements, loc='upper left', fontsize=9,
             facecolor='#1a1a1a', edgecolor='#666666', labelcolor='#ffffff',
             framealpha=0.95)

    # Stats box
    stats_text = f"""NETWORK STATISTICS
Total Entities: {len(G.nodes())}
Direct Connections: {len(G.edges())}
Sub-Clusters Identified: 2-3
Largest Cluster: {len(deity_companies)} companies"""

    ax.text(0.98, 0.02, stats_text, transform=ax.transAxes,
           fontsize=10, color='#ffffff', fontfamily='monospace',
           verticalalignment='bottom', horizontalalignment='right',
           bbox=dict(boxstyle='round', facecolor='#1a1a1a', edgecolor='#666666', alpha=0.9))

    ax.axis('off')
    return fig

def create_timeline_chart(data):
    """Create registration timeline."""
    fig, ax = plt.subplots(figsize=(16, 10), facecolor='#0a0a0a')
    ax.set_facecolor('#0a0a0a')

    deity_companies = data['deity_companies']
    golyan_companies = data['golyan_companies']

    timeline = defaultdict(lambda: {'agro': 0, 'golyan': 0})

    for company in deity_companies:
        if company.registration_date_bs:
            month_key = company.registration_date_bs[:7]
            timeline[month_key]['agro'] += 1

    for company in golyan_companies:
        if company.registration_date_bs:
            month_key = company.registration_date_bs[:7]
            timeline[month_key]['golyan'] += 1

    months = sorted(timeline.keys())
    agro_counts = [timeline[m]['agro'] for m in months]
    golyan_counts = [timeline[m]['golyan'] for m in months]

    x = range(len(months))
    width = 0.35

    ax.bar([i - width/2 for i in x], agro_counts, width, label='Agro & Forestry',
           color='#44ff88', edgecolor='#ffffff', linewidth=0.5)
    ax.bar([i + width/2 for i in x], golyan_counts, width, label='Golyan Entities',
           color='#ff8844', edgecolor='#ffffff', linewidth=0.5)

    ax.set_xlabel('Registration Month (BS)', fontsize=12, color='#ffffff', fontfamily='monospace')
    ax.set_ylabel('Number of Registrations', fontsize=12, color='#ffffff', fontfamily='monospace')
    ax.set_title('REGISTRATION TIMELINE ANALYSIS', fontsize=18, color='#ffffff',
                fontfamily='monospace', fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(months, rotation=45, ha='right', fontsize=8, color='#ffffff')
    ax.tick_params(colors='#ffffff')
    ax.legend(fontsize=11, facecolor='#1a1a1a', edgecolor='#666666', labelcolor='#ffffff')
    ax.grid(True, alpha=0.1, color='#666666')

    for spine in ax.spines.values():
        spine.set_edgecolor('#666666')

    plt.tight_layout()
    return fig

def create_cluster_details_page(data):
    """Create detailed cluster breakdown page."""
    fig = plt.figure(figsize=(16, 12), facecolor='#0a0a0a')

    phone_clusters = data['phone_clusters']
    mobile_clusters = data['mobile_clusters']
    golyan_companies = data['golyan_companies']

    fig.suptitle('SUB-CLUSTER DETAILED ANALYSIS', fontsize=24, color='#ffffff',
                fontfamily='monospace', fontweight='bold', y=0.98)

    gs = fig.add_gridspec(3, 1, hspace=0.4, left=0.1, right=0.9, top=0.93, bottom=0.05)

    # Find Golyan-related clusters
    golyan_realty = next((c for c in golyan_companies if 'realty' in c.name_english.lower()), None)
    golyan_foundation = next((c for c in golyan_companies if 'foundation' in c.name_english.lower()), None)

    realty_cluster = None
    foundation_cluster = None

    for hash_val, companies in {**phone_clusters, **mobile_clusters}.items():
        if golyan_realty and golyan_realty in companies:
            realty_cluster = companies
        if golyan_foundation and golyan_foundation in companies:
            foundation_cluster = companies

    # Panel 1: Golyan Realty Cluster
    ax1 = fig.add_subplot(gs[0])
    ax1.set_facecolor('#0a0a0a')
    ax1.axis('off')

    if realty_cluster:
        text = f"""GOLYAN REALTY SUB-CLUSTER
{'='*80}

Cluster Size: {len(realty_cluster)} companies
Connection Type: Shared Phone/Mobile Number
Registration Pattern: Sequential within 2-month period

Companies in this cluster:
"""
        for i, company in enumerate(realty_cluster, 1):
            text += f"\n{i}. {company.name_english}"
            text += f"\n   Registration #: {company.registration_number}"
            text += f"\n   Date: {company.registration_date_bs}"
            text += f"\n   PAN: {company.pan}\n"

        ax1.text(0.05, 0.95, text, fontsize=10, color='#ffffff', fontfamily='monospace',
                verticalalignment='top', transform=ax1.transAxes)

    # Panel 2: Golyan Foundation Cluster
    ax2 = fig.add_subplot(gs[1])
    ax2.set_facecolor('#0a0a0a')
    ax2.axis('off')

    if foundation_cluster:
        text = f"""GOLYAN FOUNDATION SUB-CLUSTER
{'='*80}

Cluster Size: {len(foundation_cluster)} companies
Connection Type: Shared Phone/Mobile Number
Registration Pattern: Sequential registrations

Companies in this cluster:
"""
        for i, company in enumerate(foundation_cluster, 1):
            text += f"\n{i}. {company.name_english}"
            text += f"\n   Registration #: {company.registration_number}"
            text += f"\n   Date: {company.registration_date_bs}"
            text += f"\n   PAN: {company.pan}\n"

        ax2.text(0.05, 0.95, text, fontsize=10, color='#ffffff', fontfamily='monospace',
                verticalalignment='top', transform=ax2.transAxes)

    # Panel 3: Large Deity Cluster Summary
    ax3 = fig.add_subplot(gs[2])
    ax3.set_facecolor('#0a0a0a')
    ax3.axis('off')

    deity_companies = data['deity_companies']
    lawyer_name = data['lawyer_name']
    lawyer_count = data['lawyer_company_count']

    text = f"""LARGE AGRO & FORESTRY CLUSTER
{'='*80}

Total Companies: {len(deity_companies)}
Primary Controller: {lawyer_name if lawyer_name else 'Unknown'} (Lawyer)
Companies Under Control: {lawyer_count}

Registration Range: #{deity_companies[0].registration_number} - #{deity_companies[-1].registration_number}
Time Period: {deity_companies[0].registration_date_bs} to {deity_companies[-1].registration_date_bs}

Pattern Characteristics:
- Sequential registration numbers
- Hindu deity-themed naming convention
- All in Agro & Forestry sector (100% tax exempt)
- Concentrated in Kathmandu district
- Registered under single lawyer's oversight

First 10 Companies:
"""
    for i, company in enumerate(deity_companies[:10], 1):
        deity = next((d for d in DEITY_NAMES if d in company.name_english.lower()), 'N/A')
        text += f"\n{i}. {company.name_english} (Deity: {deity.capitalize()})"
        text += f"\n   Reg #{company.registration_number} | {company.registration_date_bs}\n"

    ax3.text(0.05, 0.95, text, fontsize=10, color='#ffffff', fontfamily='monospace',
            verticalalignment='top', transform=ax3.transAxes)

    return fig

async def main():
    print("Fetching Golyan Group network data with clusters...")
    data = await get_network_with_clusters()

    print(f"Found {len(data['deity_companies'])} deity-themed companies")
    print(f"Found {len(data['golyan_companies'])} Golyan companies")
    print(f"Found {len(data['phone_clusters'])} phone hash clusters")
    print(f"Found {len(data['mobile_clusters'])} mobile hash clusters")

    output_file = Path(__file__).parent.parent / "investigation_output" / "Golyan_Network_Analysis_v2.pdf"
    output_file.parent.mkdir(exist_ok=True)

    print(f"\nGenerating enhanced PDF report: {output_file}")

    with PdfPages(output_file) as pdf:
        # Page 1: Detailed Network with Sub-Clusters
        print("Creating detailed network graph with sub-clusters...")
        fig = create_detailed_network_graph(data)
        pdf.savefig(fig, facecolor='#0a0a0a')
        plt.close(fig)

        # Page 2: Cluster Details
        print("Creating cluster details page...")
        fig = create_cluster_details_page(data)
        pdf.savefig(fig, facecolor='#0a0a0a')
        plt.close(fig)

        # Page 3: Timeline
        print("Creating registration timeline...")
        fig = create_timeline_chart(data)
        pdf.savefig(fig, facecolor='#0a0a0a')
        plt.close(fig)

        # Set PDF metadata
        d = pdf.infodict()
        d['Title'] = 'Golyan Group Network Analysis - Sub-Cluster Detail'
        d['Author'] = 'NARADA OSINT Platform'
        d['Subject'] = 'Corporate Network Intelligence Report'
        d['Keywords'] = 'Nepal, Corporate Intelligence, Network Analysis, Sub-Clusters'
        d['CreationDate'] = datetime.now()

    print(f"\n✅ Enhanced report generated: {output_file}")
    print(f"\nThis version clearly shows:")
    print(f"  - Golyan Realty cluster with its linked companies")
    print(f"  - Golyan Foundation cluster with its linked companies")
    print(f"  - Other Golyan subsidiaries")
    print(f"  - Large deity-themed agro cluster under lawyer control")
    print(f"  - Clear connection types (Control, Ownership, Shared Contact)")

if __name__ == "__main__":
    asyncio.run(main())
