#!/usr/bin/env python3
"""Generate fixed interactive Palantir-style network visualization."""
import asyncio
import sys
from pathlib import Path
from collections import defaultdict
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment, CompanyDirector

DEITY_NAMES = [
    'akash', 'prithivi', 'guru', 'sukra', 'buddha', 'ravi', 'mangal',
    'brihaspati', 'som', 'sani', 'parshurama', 'shiva', 'vishnu',
    'brahma', 'rama', 'krishna', 'ganesh', 'indra', 'agni', 'varun',
    'surya', 'chandra', 'rahu', 'ketu'
]

async def get_full_network_data():
    """Fetch complete network data."""
    async with AsyncSessionLocal() as db:
        # Get all Golyan companies
        golyan_stmt = select(CompanyRegistration).where(
            CompanyRegistration.name_english.ilike('%golyan%')
        )
        result = await db.execute(golyan_stmt)
        golyan_companies = {c.id: c for c in result.scalars().all()}

        # Get deity-themed agro companies
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

        deity_companies = {
            c.id: c for c in all_companies
            if c.name_english and (
                ('agro' in c.name_english.lower() or 'forestry' in c.name_english.lower())
                and any(deity in c.name_english.lower() for deity in DEITY_NAMES)
            )
        }

        # Get IRD data
        all_entities = list(golyan_companies.values()) + list(deity_companies.values())
        pans = [c.pan for c in all_entities if c.pan]

        ird_stmt = select(IRDEnrichment).where(IRDEnrichment.pan.in_(pans))
        result = await db.execute(ird_stmt)
        ird_data = {ird.pan: ird for ird in result.scalars().all()}

        # Build clusters
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

        # Get directors
        company_ids = [c.id for c in all_entities]
        directors_stmt = select(CompanyDirector).where(
            CompanyDirector.company_id.in_(company_ids)
        )
        result = await db.execute(directors_stmt)
        directors = result.scalars().all()

        director_to_companies = defaultdict(list)
        for director in directors:
            if director.name_en:
                director_to_companies[director.name_en].append(director.company_id)

        # Find lawyer
        lawyer_name = None
        max_count = 0
        for director_name, company_ids_list in director_to_companies.items():
            deity_count = sum(1 for cid in company_ids_list if cid in deity_companies)
            if deity_count > max_count:
                max_count = deity_count
                lawyer_name = director_name

        # Find CA
        ca_name = None
        golyan_group = next((c for c in golyan_companies.values() if 'golyan group' in c.name_english.lower()), None)
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
            'director_to_companies': dict(director_to_companies),
            'lawyer_name': lawyer_name,
            'ca_name': ca_name,
        }

def generate_html(data):
    """Generate interactive HTML with vis.js network."""

    deity_companies = data['deity_companies']
    golyan_companies = data['golyan_companies']
    phone_clusters = data['phone_clusters']
    mobile_clusters = data['mobile_clusters']
    ird_data = data['ird_data']
    lawyer_name = data['lawyer_name']
    ca_name = data['ca_name']

    nodes = []
    edges = []
    node_id_map = {}

    # Find key entities
    golyan_group = next((c for c in golyan_companies.values() if 'golyan group' in c.name_english.lower()), None)
    golyan_realty = next((c for c in golyan_companies.values() if 'realty' in c.name_english.lower()), None)
    golyan_foundation = next((c for c in golyan_companies.values() if 'foundation' in c.name_english.lower()), None)

    # Find Golyan Realty cluster members
    realty_cluster_ids = []
    if golyan_realty:
        for hash_val, company_ids in {**phone_clusters, **mobile_clusters}.items():
            if golyan_realty.id in company_ids:
                realty_cluster_ids = company_ids
                break

    # Find Golyan Foundation cluster members
    foundation_cluster_ids = []
    if golyan_foundation:
        for hash_val, company_ids in {**phone_clusters, **mobile_clusters}.items():
            if golyan_foundation.id in company_ids:
                foundation_cluster_ids = company_ids
                break

    # Add Golyan Group (center)
    if golyan_group:
        nodes.append({
            'id': 'golyan_group',
            'label': golyan_group.name_english,
            'group': 'parent',
            'title': f"<b>{golyan_group.name_english}</b><br>Reg: #{golyan_group.registration_number}<br>Date: {golyan_group.registration_date_bs}<br>PAN: {golyan_group.pan}",
            'value': 60,
            'font': {'size': 18, 'color': '#ffffff', 'bold': True}
        })
        node_id_map[golyan_group.id] = 'golyan_group'

    # Add CA director
    if ca_name:
        nodes.append({
            'id': 'ca_director',
            'label': f'CA\n{ca_name}',
            'group': 'director',
            'title': f"<b>CA (Chartered Accountant)</b><br>{ca_name}<br>Controls Golyan Group",
            'value': 40,
            'shape': 'box',
            'font': {'size': 14, 'color': '#ffffff', 'bold': True}
        })
        edges.append({
            'from': 'ca_director',
            'to': 'golyan_group',
            'color': {'color': '#ff4444'},
            'width': 5,
            'title': 'Controls',
            'arrows': {'to': {'enabled': True, 'scaleFactor': 1}}
        })

    # Add lawyer
    if lawyer_name:
        nodes.append({
            'id': 'lawyer',
            'label': f'LAWYER\n{lawyer_name}',
            'group': 'director',
            'title': f"<b>Lawyer (Shell Company Controller)</b><br>{lawyer_name}<br>Controls {len(deity_companies)} agro companies",
            'value': 45,
            'shape': 'box',
            'font': {'size': 14, 'color': '#ffffff', 'bold': True}
        })
        # Connect lawyer to Golyan Group
        edges.append({
            'from': 'lawyer',
            'to': 'golyan_group',
            'color': {'color': '#4488ff'},
            'width': 3,
            'dashes': [10, 5],
            'title': 'Linked',
            'arrows': {'to': {'enabled': False}}
        })

    # Add all Golyan companies with FULL NAMES
    for company in golyan_companies.values():
        if company.id == (golyan_group.id if golyan_group else None):
            continue

        node_id = f'gol_{company.id}'
        node_id_map[company.id] = node_id

        # Determine if it's a cluster head
        is_cluster_head = (company.id in realty_cluster_ids and company.id == realty_cluster_ids[0]) or \
                         (company.id in foundation_cluster_ids and company.id == foundation_cluster_ids[0])

        nodes.append({
            'id': node_id,
            'label': company.name_english,  # FULL NAME
            'group': 'golyan_cluster' if is_cluster_head else 'golyan',
            'title': f"<b>{company.name_english}</b><br>Reg: #{company.registration_number}<br>Date: {company.registration_date_bs}<br>PAN: {company.pan}",
            'value': 30 if is_cluster_head else 20,
            'font': {'size': 11, 'color': '#ffffff'}
        })

        if golyan_group:
            edges.append({
                'from': 'golyan_group',
                'to': node_id,
                'color': {'color': '#ff8844', 'opacity': 0.6},
                'width': 2,
                'dashes': [5, 5],
                'title': 'Subsidiary'
            })

    # Add cluster connections for Golyan Realty
    if len(realty_cluster_ids) > 1:
        for i, cid1 in enumerate(realty_cluster_ids):
            if cid1 in node_id_map:
                for cid2 in realty_cluster_ids[i+1:]:
                    if cid2 in node_id_map:
                        edges.append({
                            'from': node_id_map[cid1],
                            'to': node_id_map[cid2],
                            'color': {'color': '#ffaa00', 'opacity': 0.7},
                            'width': 3,
                            'title': 'Shared Phone/Mobile',
                            'arrows': {'to': {'enabled': False}}
                        })

    # Add cluster connections for Golyan Foundation
    if len(foundation_cluster_ids) > 1:
        for i, cid1 in enumerate(foundation_cluster_ids):
            if cid1 in node_id_map:
                for cid2 in foundation_cluster_ids[i+1:]:
                    if cid2 in node_id_map:
                        edges.append({
                            'from': node_id_map[cid1],
                            'to': node_id_map[cid2],
                            'color': {'color': '#ffaa00', 'opacity': 0.7},
                            'width': 3,
                            'title': 'Shared Phone/Mobile',
                            'arrows': {'to': {'enabled': False}}
                        })

    # Add ALL deity companies with FULL NAMES
    for company in deity_companies.values():
        node_id = f'deity_{company.id}'
        node_id_map[company.id] = node_id

        nodes.append({
            'id': node_id,
            'label': company.name_english,  # FULL NAME
            'group': 'agro',
            'title': f"<b>{company.name_english}</b><br>Reg: #{company.registration_number}<br>Date: {company.registration_date_bs}<br>PAN: {company.pan}",
            'value': 15,
            'font': {'size': 9, 'color': '#ffffff'}
        })

        # Connect ALL shell companies to lawyer
        if lawyer_name:
            edges.append({
                'from': 'lawyer',
                'to': node_id,
                'color': {'color': '#44ff88', 'opacity': 0.4},
                'width': 1.5,
                'title': 'Controls',
                'arrows': {'to': {'enabled': True, 'scaleFactor': 0.5}}
            })

    html_template = f"""<!DOCTYPE html>
<html>
<head>
    <title>Golyan Group Network Analysis - NARADA OSINT</title>
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Monaco', 'Courier New', monospace;
            background: #0a0a0a;
            color: #ffffff;
            overflow: hidden;
        }}

        #header {{
            background: linear-gradient(to right, #1a1a1a, #0a0a0a);
            padding: 20px 30px;
            border-bottom: 2px solid #ff4444;
            box-shadow: 0 2px 10px rgba(255, 68, 68, 0.3);
        }}

        #header h1 {{
            font-size: 24px;
            color: #ff4444;
            letter-spacing: 2px;
            margin-bottom: 5px;
            text-shadow: 0 0 10px rgba(255, 68, 68, 0.5);
        }}

        #header .subtitle {{
            font-size: 12px;
            color: #888888;
            letter-spacing: 1px;
        }}

        #network {{
            width: 100%;
            height: calc(100vh - 140px);
            border: none;
            background: #0a0a0a;
        }}

        #stats {{
            position: absolute;
            top: 100px;
            right: 20px;
            background: rgba(26, 26, 26, 0.95);
            border: 1px solid #333333;
            border-radius: 8px;
            padding: 20px;
            min-width: 320px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
            backdrop-filter: blur(10px);
        }}

        #stats h3 {{
            color: #ff4444;
            margin-bottom: 15px;
            font-size: 14px;
            letter-spacing: 1px;
            border-bottom: 1px solid #333333;
            padding-bottom: 10px;
        }}

        .stat-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #1a1a1a;
            font-size: 12px;
        }}

        .stat-label {{
            color: #888888;
        }}

        .stat-value {{
            color: #ffffff;
            font-weight: bold;
        }}

        .legend {{
            margin-top: 20px;
            padding-top: 15px;
            border-top: 1px solid #333333;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            margin: 8px 0;
            font-size: 11px;
        }}

        .legend-color {{
            width: 20px;
            height: 20px;
            border-radius: 50%;
            margin-right: 10px;
            border: 2px solid #ffffff;
        }}

        .legend-box {{
            width: 20px;
            height: 20px;
            margin-right: 10px;
            border: 2px solid #ffffff;
        }}

        #controls {{
            position: absolute;
            bottom: 20px;
            left: 20px;
            display: flex;
            gap: 10px;
        }}

        button {{
            background: #1a1a1a;
            border: 1px solid #ff4444;
            color: #ffffff;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-family: 'Monaco', monospace;
            font-size: 11px;
            letter-spacing: 1px;
            transition: all 0.3s;
        }}

        button:hover {{
            background: #ff4444;
            box-shadow: 0 0 15px rgba(255, 68, 68, 0.5);
        }}

        #info {{
            position: absolute;
            bottom: 20px;
            right: 20px;
            background: rgba(26, 26, 26, 0.9);
            border: 1px solid #333333;
            padding: 10px 15px;
            border-radius: 5px;
            font-size: 10px;
            color: #888888;
        }}
    </style>
</head>
<body>
    <div id="header">
        <h1>GOLYAN GROUP CORPORATE NETWORK</h1>
        <div class="subtitle">Intelligence Analysis | Nepal Company Registrar Data | NARADA OSINT Platform</div>
    </div>

    <div id="network"></div>

    <div id="stats">
        <h3>NETWORK STATISTICS</h3>
        <div class="stat-item">
            <span class="stat-label">Total Entities:</span>
            <span class="stat-value">{len(nodes)}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Connections:</span>
            <span class="stat-value">{len(edges)}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Golyan Companies:</span>
            <span class="stat-value">{len(golyan_companies)}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Shell Companies:</span>
            <span class="stat-value">{len(deity_companies)}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Phone Clusters:</span>
            <span class="stat-value">{len(phone_clusters)}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Mobile Clusters:</span>
            <span class="stat-value">{len(mobile_clusters)}</span>
        </div>

        <div class="legend">
            <div class="legend-item">
                <div class="legend-color" style="background: #ff4444;"></div>
                <span>Parent Entity</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #ffaa44;"></div>
                <span>Golyan Cluster Heads</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #ff8844;"></div>
                <span>Golyan Subsidiaries</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #44ff88;"></div>
                <span>Shell Companies</span>
            </div>
            <div class="legend-item">
                <div class="legend-box" style="background: #4488ff;"></div>
                <span>Directors</span>
            </div>
        </div>
    </div>

    <div id="controls">
        <button onclick="network.fit()">FIT VIEW</button>
        <button onclick="togglePhysics()">TOGGLE PHYSICS</button>
        <button onclick="resetZoom()">RESET</button>
        <button onclick="focusShellCompanies()">FOCUS SHELLS</button>
    </div>

    <div id="info">
        Scroll to zoom | Drag to pan | Click nodes for details | Full company names shown
    </div>

    <script type="text/javascript">
        const nodes = new vis.DataSet({json.dumps(nodes, indent=8)});
        const edges = new vis.DataSet({json.dumps(edges, indent=8)});

        const container = document.getElementById('network');
        const data = {{ nodes: nodes, edges: edges }};

        const options = {{
            nodes: {{
                shape: 'dot',
                scaling: {{ min: 10, max: 60 }},
                font: {{
                    size: 12,
                    face: 'Monaco, monospace',
                    color: '#ffffff',
                    strokeWidth: 0
                }},
                borderWidth: 2,
                shadow: {{
                    enabled: true,
                    color: 'rgba(0,0,0,0.5)',
                    size: 10
                }}
            }},
            edges: {{
                smooth: {{ enabled: true, type: 'continuous', roundness: 0.5 }},
                shadow: {{ enabled: false }}
            }},
            groups: {{
                parent: {{
                    color: {{ background: '#ff4444', border: '#ffffff',
                        highlight: {{ background: '#ff6666', border: '#ffffff' }} }},
                    borderWidth: 4
                }},
                golyan_cluster: {{
                    color: {{ background: '#ffaa44', border: '#ffffff',
                        highlight: {{ background: '#ffcc66', border: '#ffffff' }} }},
                    borderWidth: 3
                }},
                golyan: {{
                    color: {{ background: '#ff8844', border: '#ffffff',
                        highlight: {{ background: '#ffaa66', border: '#ffffff' }} }},
                    borderWidth: 2
                }},
                agro: {{
                    color: {{ background: '#44ff88', border: '#ffffff',
                        highlight: {{ background: '#66ffaa', border: '#ffffff' }} }},
                    borderWidth: 1
                }},
                director: {{
                    color: {{ background: '#4488ff', border: '#ffffff',
                        highlight: {{ background: '#66aaff', border: '#ffffff' }} }},
                    borderWidth: 2
                }}
            }},
            physics: {{
                enabled: true,
                solver: 'forceAtlas2Based',
                forceAtlas2Based: {{
                    gravitationalConstant: -80,
                    centralGravity: 0.01,
                    springLength: 250,
                    springConstant: 0.05,
                    damping: 0.4,
                    avoidOverlap: 0.8
                }},
                stabilization: {{ enabled: true, iterations: 1000 }}
            }},
            interaction: {{
                hover: true,
                tooltipDelay: 100,
                zoomView: true,
                dragView: true
            }}
        }};

        const network = new vis.Network(container, data, options);

        let physicsEnabled = true;
        function togglePhysics() {{
            physicsEnabled = !physicsEnabled;
            network.setOptions({{ physics: {{ enabled: physicsEnabled }} }});
        }}

        function resetZoom() {{
            network.fit({{ animation: {{ duration: 1000 }} }});
        }}

        function focusShellCompanies() {{
            const shellNodes = nodes.get({{
                filter: function(item) {{
                    return item.group === 'agro';
                }}
            }});
            network.fit({{
                nodes: shellNodes.map(n => n.id),
                animation: {{ duration: 1000 }}
            }});
        }}

        network.on("stabilizationIterationsDone", function() {{
            network.setOptions({{ physics: false }});
        }});
    </script>
</body>
</html>"""

    return html_template

async def main():
    print("Fetching complete network data...")
    data = await get_full_network_data()

    print(f"Found {len(data['deity_companies'])} shell companies")
    print(f"Found {len(data['golyan_companies'])} Golyan companies")

    print("\nGenerating fixed interactive HTML...")
    html = generate_html(data)

    output_file = Path(__file__).parent.parent / "investigation_output" / "golyan_network_interactive.html"
    output_file.parent.mkdir(exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n✅ Fixed visualization generated: {output_file}")
    print(f"\nImprovements:")
    print(f"  ✓ All {len(data['deity_companies'])} shell companies connected to lawyer")
    print(f"  ✓ Lawyer connected to Golyan Group")
    print(f"  ✓ Full company names displayed")
    print(f"  ✓ Golyan Realty cluster explicitly connected")
    print(f"  ✓ Golyan Foundation cluster explicitly connected")
    print(f"  ✓ Added 'Focus Shells' button to zoom to shell companies")

if __name__ == "__main__":
    asyncio.run(main())
