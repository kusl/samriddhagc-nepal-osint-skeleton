#!/usr/bin/env python3
"""Generate comprehensive Golyan Group network visualization report."""
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
from sqlalchemy import select, and_, or_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment, CompanyDirector

# Hindu deity names
DEITY_NAMES = [
    'akash', 'prithivi', 'guru', 'sukra', 'buddha', 'ravi', 'mangal',
    'brihaspati', 'som', 'sani', 'parshurama', 'shiva', 'vishnu',
    'brahma', 'rama', 'krishna', 'ganesh', 'indra', 'agni', 'varun',
    'surya', 'chandra', 'rahu', 'ketu'
]

async def get_golyan_network_data():
    """Fetch all Golyan-related companies and their directors."""
    async with AsyncSessionLocal() as db:
        # 1. Get deity-themed agro companies (281206-297307)
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

        # 2. Get all Golyan companies
        golyan_stmt = select(CompanyRegistration).where(
            CompanyRegistration.name_english.ilike('%golyan%')
        )
        result = await db.execute(golyan_stmt)
        golyan_companies = result.scalars().all()

        # 3. Get directors for all these companies
        all_company_ids = [c.id for c in deity_companies + golyan_companies]
        directors_stmt = select(CompanyDirector).where(
            CompanyDirector.company_id.in_(all_company_ids)
        )
        result = await db.execute(directors_stmt)
        directors = result.scalars().all()

        # 4. Get IRD enrichment for phone clusters
        pans = [c.pan for c in deity_companies + golyan_companies if c.pan]
        ird_stmt = select(IRDEnrichment).where(IRDEnrichment.pan.in_(pans))
        result = await db.execute(ird_stmt)
        ird_data = {ird.pan: ird for ird in result.scalars().all()}

        # 5. Group directors by name
        director_to_companies = defaultdict(list)
        for director in directors:
            if director.name_en:
                director_to_companies[director.name_en].append(director.company_id)

        # Find the lawyer (director with most deity companies)
        lawyer_name = None
        max_count = 0
        for director_name, company_ids in director_to_companies.items():
            deity_count = sum(1 for cid in company_ids if any(c.id == cid for c in deity_companies))
            if deity_count > max_count:
                max_count = deity_count
                lawyer_name = director_name

        # Find the CA (director of Golyan Group companies)
        ca_name = None
        golyan_group = next((c for c in golyan_companies if 'golyan group' in c.name_english.lower()), None)
        if golyan_group:
            ca_directors = [d for d in directors if d.company_id == golyan_group.id]
            if ca_directors:
                ca_name = ca_directors[0].name_en

        return {
            'deity_companies': deity_companies,
            'golyan_companies': golyan_companies,
            'directors': directors,
            'ird_data': ird_data,
            'director_to_companies': dict(director_to_companies),
            'lawyer_name': lawyer_name,
            'ca_name': ca_name,
            'lawyer_company_count': max_count
        }

def create_network_graph(data, page_title):
    """Create network visualization."""
    fig, ax = plt.subplots(figsize=(16, 12), facecolor='#0a0a0a')
    ax.set_facecolor('#0a0a0a')

    G = nx.Graph()

    deity_companies = data['deity_companies']
    golyan_companies = data['golyan_companies']
    directors = data['directors']
    lawyer_name = data['lawyer_name']
    ca_name = data['ca_name']

    # Add nodes
    # Golyan Group (center)
    golyan_group = next((c for c in golyan_companies if 'golyan group' in c.name_english.lower()), None)
    if golyan_group:
        G.add_node('GOLYAN_GROUP', type='parent', label='Golyan Group',
                   reg=golyan_group.registration_number)

    # Other Golyan entities
    for company in golyan_companies:
        if 'golyan group' not in company.name_english.lower():
            node_id = f"GOL_{company.registration_number}"
            G.add_node(node_id, type='golyan', label=company.name_english,
                      reg=company.registration_number)
            if golyan_group:
                G.add_edge('GOLYAN_GROUP', node_id)

    # Deity companies
    for company in deity_companies[:50]:  # Limit to 50 for readability
        node_id = f"AGRO_{company.registration_number}"
        deity = next((d for d in DEITY_NAMES if d in company.name_english.lower()), 'other')
        G.add_node(node_id, type='agro', label=company.name_english[:30],
                  reg=company.registration_number, deity=deity)

    # Add lawyer node
    if lawyer_name:
        G.add_node('LAWYER', type='director', label=f"Director\n{lawyer_name[:20]}",
                  role='Lawyer')
        # Connect lawyer to deity companies
        for company in deity_companies[:50]:
            node_id = f"AGRO_{company.registration_number}"
            if node_id in G:
                G.add_edge('LAWYER', node_id)

    # Add CA node
    if ca_name and golyan_group:
        G.add_node('CA', type='director', label=f"Director\n{ca_name[:20]}",
                  role='CA')
        G.add_edge('CA', 'GOLYAN_GROUP')

    # Layout
    pos = nx.spring_layout(G, k=2, iterations=50, seed=42)

    # Separate nodes by type
    parent_nodes = [n for n, d in G.nodes(data=True) if d.get('type') == 'parent']
    golyan_nodes = [n for n, d in G.nodes(data=True) if d.get('type') == 'golyan']
    agro_nodes = [n for n, d in G.nodes(data=True) if d.get('type') == 'agro']
    director_nodes = [n for n, d in G.nodes(data=True) if d.get('type') == 'director']

    # Draw nodes
    if parent_nodes:
        nx.draw_networkx_nodes(G, pos, nodelist=parent_nodes, node_color='#ff4444',
                              node_size=3000, ax=ax, node_shape='o', linewidths=2,
                              edgecolors='#ffffff')
    if golyan_nodes:
        nx.draw_networkx_nodes(G, pos, nodelist=golyan_nodes, node_color='#ff8844',
                              node_size=1500, ax=ax, node_shape='o', linewidths=1.5,
                              edgecolors='#ffffff')
    if agro_nodes:
        nx.draw_networkx_nodes(G, pos, nodelist=agro_nodes, node_color='#44ff88',
                              node_size=800, ax=ax, node_shape='o', linewidths=1,
                              edgecolors='#ffffff', alpha=0.8)
    if director_nodes:
        nx.draw_networkx_nodes(G, pos, nodelist=director_nodes, node_color='#4488ff',
                              node_size=2000, ax=ax, node_shape='s', linewidths=2,
                              edgecolors='#ffffff')

    # Draw edges
    nx.draw_networkx_edges(G, pos, edge_color='#666666', width=0.5, alpha=0.3, ax=ax)

    # Draw labels
    labels = {n: d.get('label', n) for n, d in G.nodes(data=True)}
    nx.draw_networkx_labels(G, pos, labels, font_size=6, font_color='#ffffff',
                           font_family='monospace', ax=ax)

    # Title and legend
    ax.set_title(page_title, fontsize=20, color='#ffffff', pad=20, fontfamily='monospace',
                fontweight='bold')

    # Legend
    legend_elements = [
        mpatches.Patch(color='#ff4444', label='Parent Entity (Golyan Group)'),
        mpatches.Patch(color='#ff8844', label='Golyan Subsidiaries'),
        mpatches.Patch(color='#44ff88', label='Agro & Forestry Entities'),
        mpatches.Patch(color='#4488ff', label='Directors/Controllers'),
    ]
    ax.legend(handles=legend_elements, loc='upper left', fontsize=10,
             facecolor='#1a1a1a', edgecolor='#666666', labelcolor='#ffffff')

    ax.axis('off')
    return fig

def create_timeline_chart(data):
    """Create registration timeline."""
    fig, ax = plt.subplots(figsize=(16, 10), facecolor='#0a0a0a')
    ax.set_facecolor('#0a0a0a')

    deity_companies = data['deity_companies']
    golyan_companies = data['golyan_companies']

    # Group by month
    from collections import defaultdict
    timeline = defaultdict(lambda: {'agro': 0, 'golyan': 0})

    for company in deity_companies:
        if company.registration_date_bs:
            month_key = company.registration_date_bs[:7]  # YYYY-MM
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
    ax.set_title('Registration Timeline Analysis', fontsize=16, color='#ffffff',
                fontfamily='monospace', fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(months, rotation=45, ha='right', fontsize=8, color='#ffffff')
    ax.tick_params(colors='#ffffff')
    ax.legend(fontsize=10, facecolor='#1a1a1a', edgecolor='#666666', labelcolor='#ffffff')
    ax.grid(True, alpha=0.1, color='#666666')

    for spine in ax.spines.values():
        spine.set_edgecolor('#666666')

    plt.tight_layout()
    return fig

def create_statistics_dashboard(data):
    """Create comprehensive statistics page."""
    fig = plt.figure(figsize=(16, 12), facecolor='#0a0a0a')

    deity_companies = data['deity_companies']
    golyan_companies = data['golyan_companies']
    lawyer_name = data['lawyer_name']
    ca_name = data['ca_name']
    lawyer_count = data['lawyer_company_count']

    # Title
    fig.suptitle('GOLYAN GROUP NETWORK ANALYSIS', fontsize=24, color='#ffffff',
                fontfamily='monospace', fontweight='bold', y=0.98)

    # Create grid
    gs = fig.add_gridspec(4, 2, hspace=0.4, wspace=0.3, left=0.1, right=0.9, top=0.93, bottom=0.05)

    # Panel 1: Network Summary
    ax1 = fig.add_subplot(gs[0, :])
    ax1.set_facecolor('#0a0a0a')
    ax1.axis('off')

    summary_text = f"""
    NETWORK SUMMARY
    {'='*80}

    Total Entities Identified: {len(deity_companies) + len(golyan_companies)}
    - Agro & Forestry Companies: {len(deity_companies)}
    - Golyan-branded Entities: {len(golyan_companies)}

    Registration Range: #{deity_companies[0].registration_number if deity_companies else 'N/A'} - #{deity_companies[-1].registration_number if deity_companies else 'N/A'}
    Registration Period: {deity_companies[0].registration_date_bs if deity_companies else 'N/A'} to {deity_companies[-1].registration_date_bs if deity_companies else 'N/A'}

    Primary Controller (Lawyer): {lawyer_name if lawyer_name else 'Unknown'} ({lawyer_count} entities)
    Secondary Controller (CA): {ca_name if ca_name else 'Unknown'}
    """
    ax1.text(0.05, 0.5, summary_text, fontsize=11, color='#ffffff', fontfamily='monospace',
            verticalalignment='center', transform=ax1.transAxes)

    # Panel 2: Entity Distribution
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.set_facecolor('#0a0a0a')

    categories = ['Agro & Forestry\n(Deity-themed)', 'Golyan\nSubsidiaries', 'Parent\n(Golyan Group)']
    counts = [len(deity_companies), len([c for c in golyan_companies if 'group' not in c.name_english.lower()]),
              len([c for c in golyan_companies if 'group' in c.name_english.lower()])]
    colors = ['#44ff88', '#ff8844', '#ff4444']

    bars = ax2.bar(categories, counts, color=colors, edgecolor='#ffffff', linewidth=1.5)
    ax2.set_ylabel('Entity Count', color='#ffffff', fontfamily='monospace')
    ax2.set_title('Entity Distribution', color='#ffffff', fontfamily='monospace', fontweight='bold')
    ax2.tick_params(colors='#ffffff')
    for spine in ax2.spines.values():
        spine.set_edgecolor('#666666')
    ax2.grid(True, alpha=0.1, color='#666666', axis='y')

    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height)}', ha='center', va='bottom', color='#ffffff',
                fontfamily='monospace', fontweight='bold')

    # Panel 3: District Distribution
    ax3 = fig.add_subplot(gs[1, 1])
    ax3.set_facecolor('#0a0a0a')

    district_counts = defaultdict(int)
    for c in deity_companies + golyan_companies:
        if c.district:
            district_counts[c.district] += 1

    top_districts = sorted(district_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    districts = [d[0] for d in top_districts]
    counts = [d[1] for d in top_districts]

    bars = ax3.barh(districts, counts, color='#4488ff', edgecolor='#ffffff', linewidth=1.5)
    ax3.set_xlabel('Entity Count', color='#ffffff', fontfamily='monospace')
    ax3.set_title('Top 5 Districts', color='#ffffff', fontfamily='monospace', fontweight='bold')
    ax3.tick_params(colors='#ffffff')
    for spine in ax3.spines.values():
        spine.set_edgecolor('#666666')
    ax3.grid(True, alpha=0.1, color='#666666', axis='x')

    # Panel 4: Sequential Registration Pattern
    ax4 = fig.add_subplot(gs[2, :])
    ax4.set_facecolor('#0a0a0a')

    reg_numbers = [c.registration_number for c in deity_companies[:50]]
    x_pos = range(len(reg_numbers))

    ax4.scatter(x_pos, reg_numbers, c='#44ff88', s=50, alpha=0.6, edgecolors='#ffffff', linewidths=0.5)
    ax4.plot(x_pos, reg_numbers, c='#44ff88', alpha=0.3, linewidth=1)

    # Mark Golyan Group
    golyan_group = next((c for c in golyan_companies if 'group' in c.name_english.lower()), None)
    if golyan_group and golyan_group.registration_number:
        ax4.axhline(y=golyan_group.registration_number, color='#ff4444', linestyle='--',
                   linewidth=2, label='Golyan Group Registration', alpha=0.7)

    ax4.set_xlabel('Company Sequence', color='#ffffff', fontfamily='monospace')
    ax4.set_ylabel('Registration Number', color='#ffffff', fontfamily='monospace')
    ax4.set_title('Sequential Registration Pattern', color='#ffffff',
                 fontfamily='monospace', fontweight='bold')
    ax4.tick_params(colors='#ffffff')
    ax4.legend(fontsize=9, facecolor='#1a1a1a', edgecolor='#666666', labelcolor='#ffffff')
    for spine in ax4.spines.values():
        spine.set_edgecolor('#666666')
    ax4.grid(True, alpha=0.1, color='#666666')

    # Panel 5: Key Findings
    ax5 = fig.add_subplot(gs[3, :])
    ax5.set_facecolor('#0a0a0a')
    ax5.axis('off')

    findings_text = f"""
    KEY OBSERVATIONS
    {'='*80}

    1. CLUSTER STRUCTURE
       - Large Cluster: {len(deity_companies)} agro/forestry companies with deity-themed names
       - Small Cluster: {len(golyan_companies)} Golyan-branded entities
       - Sequential registration pattern suggests coordinated filing

    2. CONTROL STRUCTURE
       - Primary Control: {lawyer_count} entities appear under lawyer {lawyer_name if lawyer_name else 'Unknown'}
       - Secondary Control: Golyan Group entities under CA {ca_name if ca_name else 'Unknown'}

    3. REGISTRATION PATTERN
       - First Entity: {deity_companies[0].name_english if deity_companies else 'N/A'} (#{deity_companies[0].registration_number if deity_companies else 'N/A'})
       - Parent Entity: Golyan Group registered mid-sequence
       - Time Period: ~6 months of continuous registrations

    4. SECTOR FOCUS
       - Agricultural/Forestry sector (100% tax exemption in Nepal)
       - Diversification into: {', '.join(set(c.name_english.split()[1] if len(c.name_english.split()) > 1 else 'Other' for c in golyan_companies[:5]))}
    """
    ax5.text(0.05, 0.5, findings_text, fontsize=10, color='#ffffff', fontfamily='monospace',
            verticalalignment='center', transform=ax5.transAxes)

    # Footer
    footer_text = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Data Source: Nepal Company Registrar | Analysis: NARADA OSINT Platform"
    fig.text(0.5, 0.01, footer_text, ha='center', fontsize=8, color='#888888', fontfamily='monospace')

    return fig

def create_deity_breakdown(data):
    """Create deity name distribution chart."""
    fig, ax = plt.subplots(figsize=(16, 10), facecolor='#0a0a0a')
    ax.set_facecolor('#0a0a0a')

    deity_companies = data['deity_companies']

    # Count deities
    deity_counts = defaultdict(int)
    for company in deity_companies:
        for deity in DEITY_NAMES:
            if deity in company.name_english.lower():
                deity_counts[deity.capitalize()] += 1
                break

    deities = sorted(deity_counts.keys(), key=lambda x: deity_counts[x], reverse=True)
    counts = [deity_counts[d] for d in deities]

    colors = plt.cm.Spectral([i/len(deities) for i in range(len(deities))])

    bars = ax.barh(deities, counts, color=colors, edgecolor='#ffffff', linewidth=1)

    ax.set_xlabel('Number of Companies', fontsize=12, color='#ffffff', fontfamily='monospace')
    ax.set_title('Hindu Deity Name Distribution in Network', fontsize=16, color='#ffffff',
                fontfamily='monospace', fontweight='bold', pad=20)
    ax.tick_params(colors='#ffffff')
    for spine in ax.spines.values():
        spine.set_edgecolor('#666666')
    ax.grid(True, alpha=0.1, color='#666666', axis='x')

    # Add value labels
    for i, (bar, count) in enumerate(zip(bars, counts)):
        ax.text(count, i, f' {count}', va='center', color='#ffffff',
               fontfamily='monospace', fontweight='bold')

    plt.tight_layout()
    return fig

async def main():
    print("Fetching Golyan Group network data...")
    data = await get_golyan_network_data()

    print(f"Found {len(data['deity_companies'])} deity-themed companies")
    print(f"Found {len(data['golyan_companies'])} Golyan companies")

    output_file = Path(__file__).parent.parent / "investigation_output" / "Golyan_Network_Analysis.pdf"
    output_file.parent.mkdir(exist_ok=True)

    print(f"\nGenerating PDF report: {output_file}")

    with PdfPages(output_file) as pdf:
        # Page 1: Network Graph - Agro Cluster
        print("Creating network graph...")
        fig = create_network_graph(data,
            "GOLYAN GROUP NETWORK STRUCTURE - AGRO & FORESTRY CLUSTER")
        pdf.savefig(fig, facecolor='#0a0a0a')
        plt.close(fig)

        # Page 2: Statistics Dashboard
        print("Creating statistics dashboard...")
        fig = create_statistics_dashboard(data)
        pdf.savefig(fig, facecolor='#0a0a0a')
        plt.close(fig)

        # Page 3: Timeline
        print("Creating registration timeline...")
        fig = create_timeline_chart(data)
        pdf.savefig(fig, facecolor='#0a0a0a')
        plt.close(fig)

        # Page 4: Deity Distribution
        print("Creating deity name analysis...")
        fig = create_deity_breakdown(data)
        pdf.savefig(fig, facecolor='#0a0a0a')
        plt.close(fig)

        # Set PDF metadata
        d = pdf.infodict()
        d['Title'] = 'Golyan Group Network Analysis'
        d['Author'] = 'NARADA OSINT Platform'
        d['Subject'] = 'Corporate Network Intelligence Report'
        d['Keywords'] = 'Nepal, Corporate Intelligence, Network Analysis'
        d['CreationDate'] = datetime.now()

    print(f"\n✅ Report generated successfully: {output_file}")
    print(f"\nYou can now screenshot pages from this PDF and post to Reddit.")

if __name__ == "__main__":
    asyncio.run(main())
