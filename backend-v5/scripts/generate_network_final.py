#!/usr/bin/env python3
"""Generate network visualization without relying on missing director data."""
import asyncio
import sys
from pathlib import Path
from collections import defaultdict
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment, CompanyDirector

# Shell company name patterns
SHELL_PATTERNS = ['agro', 'forestry']

async def get_network_data():
    async with AsyncSessionLocal() as db:
        # Get Golyan companies
        golyan_stmt = select(CompanyRegistration).where(
            CompanyRegistration.name_english.ilike('%golyan%')
        )
        result = await db.execute(golyan_stmt)
        golyan_companies = {c.id: c for c in result.scalars().all()}

        # Get all shell companies in the registration range (excluding Golyan companies)
        shell_stmt = select(CompanyRegistration).where(
            and_(
                CompanyRegistration.registration_number >= 281206,
                CompanyRegistration.registration_number <= 304643,  # Extended range to include CA cluster
            )
        )
        result = await db.execute(shell_stmt)
        all_companies = result.scalars().all()

        # Get ALL companies in registration range (we'll filter later based on cluster membership)
        all_companies_dict = {c.id: c for c in all_companies}

        # Get IRD data for ALL companies to find clusters
        all_entities = list(golyan_companies.values()) + list(all_companies_dict.values())
        pans = [c.pan for c in all_entities if c.pan]

        ird_stmt = select(IRDEnrichment).where(IRDEnrichment.pan.in_(pans))
        result = await db.execute(ird_stmt)
        ird_data = {ird.pan: ird for ird in result.scalars().all()}

        # Build clusters based on phone/mobile hash
        phone_clusters = defaultdict(list)
        mobile_clusters = defaultdict(list)

        for company in all_entities:
            if company.pan and company.pan in ird_data:
                ird = ird_data[company.pan]
                if ird.phone_hash:
                    phone_clusters[ird.phone_hash].append(company.id)
                if ird.mobile_hash:
                    mobile_clusters[ird.mobile_hash].append(company.id)

        phone_clusters = {h: ids for h, ids in phone_clusters.items() if len(ids) > 1}
        mobile_clusters = {h: ids for h, ids in mobile_clusters.items() if len(ids) > 1}

        # Identify lawyer cluster (contains Golyan Group + shell companies)
        golyan_group_temp = next((c for c in golyan_companies.values() if 'golyan group' in c.name_english.lower()), None)
        lawyer_cluster_ids = []
        ca_cluster_ids = []

        if golyan_group_temp:
            # Find which cluster contains Golyan Group
            for hash_val, company_ids in {**phone_clusters, **mobile_clusters}.items():
                if golyan_group_temp.id in company_ids:
                    lawyer_cluster_ids = company_ids
                    break

        # Find CA cluster (contains Golyan Realty/Power)
        golyan_realty_temp = next((c for c in golyan_companies.values() if 'realty' in c.name_english.lower()), None)
        if golyan_realty_temp:
            for hash_val, company_ids in {**phone_clusters, **mobile_clusters}.items():
                if golyan_realty_temp.id in company_ids:
                    ca_cluster_ids = company_ids
                    break

        # NOW filter shell companies - only include those in lawyer or CA clusters
        shell_companies = {
            c.id: c for c in all_companies_dict.values()
            if c.id in (lawyer_cluster_ids + ca_cluster_ids)  # Must be in one of the clusters
            and c.name_english
            and ('agro' in c.name_english.lower() or 'forestry' in c.name_english.lower())
            and 'golyan' not in c.name_english.lower()  # Exclude Golyan-branded companies
        }

        # Get CA for Golyan Group
        golyan_group = next((c for c in golyan_companies.values() if 'golyan group' in c.name_english.lower()), None)
        ca_name = None
        if golyan_group:
            directors_stmt = select(CompanyDirector).where(CompanyDirector.company_id == golyan_group.id)
            result = await db.execute(directors_stmt)
            directors = result.scalars().all()
            if directors:
                ca_name = directors[0].name_en

        return {
            'shell_companies': shell_companies,
            'golyan_companies': golyan_companies,
            'phone_clusters': phone_clusters,
            'mobile_clusters': mobile_clusters,
            'ird_data': ird_data,
            'ca_name': ca_name,
            'lawyer_cluster_ids': lawyer_cluster_ids,
            'ca_cluster_ids': ca_cluster_ids,
        }

def generate_html(data):
    shell_companies = data['shell_companies']
    golyan_companies = data['golyan_companies']
    phone_clusters = data['phone_clusters']
    mobile_clusters = data['mobile_clusters']
    ca_name = data['ca_name']
    lawyer_cluster_ids = data['lawyer_cluster_ids']
    ca_cluster_ids = data['ca_cluster_ids']

    nodes = []
    edges = []
    node_id_map = {}

    # Find key entities
    golyan_group = next((c for c in golyan_companies.values() if 'golyan group' in c.name_english.lower()), None)
    golyan_realty = next((c for c in golyan_companies.values() if 'realty' in c.name_english.lower()), None)
    golyan_foundation = next((c for c in golyan_companies.values() if 'foundation' in c.name_english.lower()), None)

    # Find cluster members
    realty_cluster_ids = []
    foundation_cluster_ids = []

    if golyan_realty:
        for hash_val, company_ids in {**phone_clusters, **mobile_clusters}.items():
            if golyan_realty.id in company_ids:
                realty_cluster_ids = company_ids
                break

    if golyan_foundation:
        for hash_val, company_ids in {**phone_clusters, **mobile_clusters}.items():
            if golyan_foundation.id in company_ids:
                foundation_cluster_ids = company_ids
                break

    # Add Golyan Group
    if golyan_group:
        nodes.append({
            'id': 'golyan_group',
            'label': golyan_group.name_english,
            'group': 'parent',
            'title': f"<b>{golyan_group.name_english}</b><br>Reg: #{golyan_group.registration_number}<br>Date: {golyan_group.registration_date_bs}<br>PAN: {golyan_group.pan}",
            'value': 70,
            'font': {'size': 20, 'color': '#ffffff', 'bold': True}
        })
        node_id_map[golyan_group.id] = 'golyan_group'

    # Identify which Golyan entities are in which cluster
    golyan_in_lawyer_cluster = [cid for cid in lawyer_cluster_ids if cid in golyan_companies]
    golyan_in_ca_cluster = [cid for cid in ca_cluster_ids if cid in golyan_companies]

    # Add all Golyan companies
    for company in golyan_companies.values():
        if company.id == (golyan_group.id if golyan_group else None):
            continue

        node_id = f'gol_{company.id}'
        node_id_map[company.id] = node_id

        is_cluster_head = (company.id in realty_cluster_ids and len(realty_cluster_ids) > 1) or \
                         (company.id in foundation_cluster_ids and len(foundation_cluster_ids) > 1)

        nodes.append({
            'id': node_id,
            'label': company.name_english,
            'group': 'golyan_cluster' if is_cluster_head else 'golyan',
            'title': f"<b>{company.name_english}</b><br>Reg: #{company.registration_number}<br>Date: {company.registration_date_bs}<br>PAN: {company.pan}",
            'value': 35 if is_cluster_head else 25,
            'font': {'size': 12, 'color': '#ffffff'}
        })

        if golyan_group:
            # Check which cluster this company belongs to
            if company.id in ca_cluster_ids:
                # CA cluster member - red edge
                edges.append({
                    'from': node_id,
                    'to': 'golyan_group',
                    'color': {'color': '#ff4444'},
                    'width': 4,
                    'title': 'CA Cluster',
                    'arrows': {'to': False},
                    'smooth': {'type': 'curvedCCW', 'roundness': 0.2}
                })
            elif company.id in lawyer_cluster_ids:
                # Lawyer cluster member - green edge
                edges.append({
                    'from': node_id,
                    'to': 'golyan_group',
                    'color': {'color': '#44ff88'},
                    'width': 4,
                    'title': 'Lawyer Cluster',
                    'arrows': {'to': False},
                    'smooth': {'type': 'curvedCW', 'roundness': 0.2}
                })
            else:
                # Regular subsidiary edge
                edges.append({
                    'from': 'golyan_group',
                    'to': node_id,
                    'color': {'color': '#ff8844', 'opacity': 0.6},
                    'width': 2,
                    'dashes': [5, 5],
                    'title': 'Subsidiary'
                })

    # Add cluster connections
    if len(realty_cluster_ids) > 1:
        for i, cid1 in enumerate(realty_cluster_ids):
            if cid1 in node_id_map:
                for cid2 in realty_cluster_ids[i+1:]:
                    if cid2 in node_id_map:
                        edges.append({
                            'from': node_id_map[cid1],
                            'to': node_id_map[cid2],
                            'color': {'color': '#ffaa00'},
                            'width': 3,
                            'title': 'Shared Contact',
                            'arrows': {'to': False}
                        })

    if len(foundation_cluster_ids) > 1:
        for i, cid1 in enumerate(foundation_cluster_ids):
            if cid1 in node_id_map:
                for cid2 in foundation_cluster_ids[i+1:]:
                    if cid2 in node_id_map:
                        edges.append({
                            'from': node_id_map[cid1],
                            'to': node_id_map[cid2],
                            'color': {'color': '#ffaa00'},
                            'width': 3,
                            'title': 'Shared Contact',
                            'arrows': {'to': False}
                        })

    # Add ALL shell companies (agro/forestry)
    for company in shell_companies.values():
        node_id = f'shell_{company.id}'
        node_id_map[company.id] = node_id

        # Determine which cluster this shell company belongs to
        in_lawyer_cluster = company.id in lawyer_cluster_ids
        in_ca_cluster = company.id in ca_cluster_ids

        # Color based on cluster membership
        if in_ca_cluster:
            group = 'ca_shell'
        elif in_lawyer_cluster:
            group = 'lawyer_shell'
        else:
            group = 'agro'

        nodes.append({
            'id': node_id,
            'label': company.name_english,
            'group': group,
            'title': f"<b>{company.name_english}</b><br>Reg: #{company.registration_number}<br>Date: {company.registration_date_bs}<br>PAN: {company.pan or 'N/A'}<br>Cluster: {'CA' if in_ca_cluster else 'Lawyer' if in_lawyer_cluster else 'None'}",
            'value': 15,
            'font': {'size': 9, 'color': '#ffffff'}
        })

        # Connect to Golyan Group based on cluster membership
        if golyan_group:
            if in_ca_cluster:
                # CA cluster - red edge
                edges.append({
                    'from': node_id,
                    'to': 'golyan_group',
                    'color': {'color': '#ff4444'},
                    'width': 2,
                    'title': 'CA Cluster',
                    'arrows': {'to': False},
                    'smooth': {'type': 'curvedCCW', 'roundness': 0.2}
                })
            elif in_lawyer_cluster:
                # Lawyer cluster - green edge
                edges.append({
                    'from': node_id,
                    'to': 'golyan_group',
                    'color': {'color': '#44ff88'},
                    'width': 2,
                    'title': 'Lawyer Cluster',
                    'arrows': {'to': False},
                    'smooth': {'type': 'curvedCW', 'roundness': 0.2}
                })

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Golyan Group Network - NARADA OSINT</title>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: Monaco, monospace; background: #0a0a0a; color: #fff; overflow: hidden; }}
        #header {{ background: linear-gradient(to right, #1a1a1a, #0a0a0a); padding: 20px 30px; border-bottom: 2px solid #ff4444; }}
        #header h1 {{ font-size: 24px; color: #ff4444; letter-spacing: 2px; text-shadow: 0 0 10px rgba(255,68,68,0.5); }}
        #header .subtitle {{ font-size: 12px; color: #888; letter-spacing: 1px; margin-top: 5px; }}
        #network {{ width: 100%; height: calc(100vh - 140px); background: #0a0a0a; }}
        #stats {{ position: absolute; top: 100px; right: 20px; background: rgba(26,26,26,0.95); border: 1px solid #333; border-radius: 8px; padding: 20px; min-width: 320px; backdrop-filter: blur(10px); }}
        #stats h3 {{ color: #ff4444; margin-bottom: 15px; font-size: 14px; border-bottom: 1px solid #333; padding-bottom: 10px; }}
        .stat-item {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #1a1a1a; font-size: 12px; }}
        .stat-label {{ color: #888; }}
        .stat-value {{ color: #fff; font-weight: bold; }}
        .legend {{ margin-top: 20px; padding-top: 15px; border-top: 1px solid #333; }}
        .legend-item {{ display: flex; align-items: center; margin: 8px 0; font-size: 11px; }}
        .legend-color {{ width: 20px; height: 20px; border-radius: 50%; margin-right: 10px; border: 2px solid #fff; }}
        .legend-box {{ width: 20px; height: 20px; margin-right: 10px; border: 2px solid #fff; }}
        #controls {{ position: absolute; bottom: 20px; left: 20px; display: flex; gap: 10px; }}
        button {{ background: #1a1a1a; border: 1px solid #ff4444; color: #fff; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-family: Monaco; font-size: 11px; letter-spacing: 1px; transition: all 0.3s; }}
        button:hover {{ background: #ff4444; box-shadow: 0 0 15px rgba(255,68,68,0.5); }}
        #info {{ position: absolute; bottom: 20px; right: 20px; background: rgba(26,26,26,0.9); border: 1px solid #333; padding: 10px 15px; border-radius: 5px; font-size: 10px; color: #888; }}
    </style>
</head>
<body>
    <div id="header">
        <h1>GOLYAN GROUP CORPORATE NETWORK</h1>
        <div class="subtitle">Intelligence Analysis | {len(nodes)} Entities | {len(edges)} Connections | NARADA OSINT</div>
    </div>
    <div id="network"></div>
    <div id="stats">
        <h3>NETWORK STATISTICS</h3>
        <div class="stat-item"><span class="stat-label">Total Entities:</span><span class="stat-value">{len(nodes)}</span></div>
        <div class="stat-item"><span class="stat-label">Connections:</span><span class="stat-value">{len(edges)}</span></div>
        <div class="stat-item"><span class="stat-label">Golyan Companies:</span><span class="stat-value">{len(golyan_companies)}</span></div>
        <div class="stat-item"><span class="stat-label">Shell Companies:</span><span class="stat-value">{len(shell_companies)}</span></div>
        <div class="stat-item"><span class="stat-label">Lawyer Cluster:</span><span class="stat-value">{len(lawyer_cluster_ids)} entities</span></div>
        <div class="stat-item"><span class="stat-label">CA Cluster:</span><span class="stat-value">{len(ca_cluster_ids)} entities</span></div>
        <div class="legend">
            <div class="legend-item"><div class="legend-color" style="background: #ff4444;"></div><span>Golyan Group</span></div>
            <div class="legend-item"><div class="legend-color" style="background: #ffaa44;"></div><span>Sub-cluster Heads</span></div>
            <div class="legend-item"><div class="legend-color" style="background: #ff8844;"></div><span>Golyan Entities</span></div>
            <div class="legend-item"><div class="legend-color" style="background: #44ff88;"></div><span>Lawyer Cluster Shells</span></div>
            <div class="legend-item"><div class="legend-color" style="background: #ff6666;"></div><span>CA Cluster Shells</span></div>
            <div class="legend-item"><div style="width: 40px; height: 3px; background: #44ff88; margin-right: 10px;"></div><span>Lawyer's Phone</span></div>
            <div class="legend-item"><div style="width: 40px; height: 3px; background: #ff4444; margin-right: 10px;"></div><span>CA's Phone</span></div>
        </div>
    </div>
    <div id="controls">
        <button onclick="network.fit()">FIT VIEW</button>
        <button onclick="togglePhysics()">TOGGLE PHYSICS</button>
        <button onclick="focusShells()">FOCUS SHELLS</button>
    </div>
    <div id="info">Drag nodes | Scroll to zoom | Hover for details | {len(shell_companies)} shell companies | Lawyer cluster: {len(lawyer_cluster_ids)} | CA cluster: {len(ca_cluster_ids)}</div>
    <script>
        const nodes = new vis.DataSet({json.dumps(nodes, indent=4)});
        const edges = new vis.DataSet({json.dumps(edges, indent=4)});
        const container = document.getElementById('network');
        const data = {{ nodes, edges }};
        const options = {{
            nodes: {{ shape: 'dot', scaling: {{ min: 10, max: 70 }}, font: {{ size: 12, face: 'Monaco', color: '#fff' }}, borderWidth: 2, shadow: {{ enabled: true, size: 10 }} }},
            edges: {{ smooth: {{ enabled: true, type: 'continuous', roundness: 0.5 }} }},
            groups: {{
                parent: {{ color: {{ background: '#ff4444', border: '#fff', highlight: {{ background: '#ff6666' }} }}, borderWidth: 4 }},
                golyan_cluster: {{ color: {{ background: '#ffaa44', border: '#fff', highlight: {{ background: '#ffcc66' }} }}, borderWidth: 3 }},
                golyan: {{ color: {{ background: '#ff8844', border: '#fff', highlight: {{ background: '#ffaa66' }} }}, borderWidth: 2 }},
                lawyer_shell: {{ color: {{ background: '#44ff88', border: '#fff', highlight: {{ background: '#66ffaa' }} }}, borderWidth: 1 }},
                ca_shell: {{ color: {{ background: '#ff6666', border: '#fff', highlight: {{ background: '#ff8888' }} }}, borderWidth: 1 }},
                agro: {{ color: {{ background: '#888888', border: '#fff', highlight: {{ background: '#aaaaaa' }} }}, borderWidth: 1 }}
            }},
            physics: {{ enabled: true, solver: 'forceAtlas2Based', forceAtlas2Based: {{ gravitationalConstant: -80, centralGravity: 0.005, springLength: 250, springConstant: 0.04, damping: 0.4, avoidOverlap: 0.9 }}, stabilization: {{ iterations: 1000 }} }},
            interaction: {{ hover: true, tooltipDelay: 100 }}
        }};
        const network = new vis.Network(container, data, options);
        let physicsEnabled = true;
        function togglePhysics() {{ physicsEnabled = !physicsEnabled; network.setOptions({{ physics: {{ enabled: physicsEnabled }} }}); }}
        function focusShells() {{ network.fit({{ nodes: nodes.get({{ filter: i => i.group === 'agro' }}).map(n => n.id), animation: {{ duration: 1000 }} }}); }}
        network.on("stabilizationIterationsDone", () => network.setOptions({{ physics: false }}));
    </script>
</body>
</html>"""
    return html

async def main():
    print("Fetching network data...")
    data = await get_network_data()
    print(f"  - {len(data['shell_companies'])} shell companies")
    print(f"  - {len(data['golyan_companies'])} Golyan companies")
    print(f"  - Lawyer cluster: {len(data['lawyer_cluster_ids'])} entities")
    print(f"  - CA cluster: {len(data['ca_cluster_ids'])} entities")

    html = generate_html(data)

    output_file = Path(__file__).parent.parent / "investigation_output" / "golyan_network_interactive.html"
    output_file.parent.mkdir(exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n✅ Generated: {output_file}")
    print(f"\nShowing {len(data['shell_companies'])} shell companies in 2 phone-based clusters!")

if __name__ == "__main__":
    asyncio.run(main())
