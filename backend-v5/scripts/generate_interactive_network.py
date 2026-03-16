#!/usr/bin/env python3
"""Generate interactive Palantir-style network visualization."""
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

        # Find lawyer (most deity companies)
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

    # Build nodes and edges
    nodes = []
    edges = []
    node_id_map = {}

    # Add Golyan Group (center)
    golyan_group = next((c for c in golyan_companies.values() if 'golyan group' in c.name_english.lower()), None)
    if golyan_group:
        nodes.append({
            'id': 'golyan_group',
            'label': 'GOLYAN\nGROUP',
            'group': 'parent',
            'title': f"<b>{golyan_group.name_english}</b><br>Reg: #{golyan_group.registration_number}<br>PAN: {golyan_group.pan}",
            'value': 50,
            'font': {'size': 16, 'color': '#ffffff', 'bold': True}
        })
        node_id_map[golyan_group.id] = 'golyan_group'

    # Add CA director
    if ca_name:
        nodes.append({
            'id': 'ca_director',
            'label': f'CA\n{ca_name.split()[0]}',
            'group': 'director',
            'title': f"<b>CA (Chartered Accountant)</b><br>{ca_name}",
            'value': 35,
            'shape': 'box',
            'font': {'size': 14, 'color': '#ffffff', 'bold': True}
        })
        edges.append({
            'from': 'ca_director',
            'to': 'golyan_group',
            'color': {'color': '#ff4444'},
            'width': 4,
            'title': 'Controls'
        })

    # Add all Golyan companies
    for company in golyan_companies.values():
        if company.id == golyan_group.id if golyan_group else False:
            continue

        node_id = f'gol_{company.id}'
        node_id_map[company.id] = node_id

        short_name = company.name_english.replace('Golyan ', '').replace(' and Forestry', '')[:20]
        nodes.append({
            'id': node_id,
            'label': short_name,
            'group': 'golyan',
            'title': f"<b>{company.name_english}</b><br>Reg: #{company.registration_number}<br>Date: {company.registration_date_bs}<br>PAN: {company.pan}",
            'value': 20,
            'font': {'size': 10, 'color': '#ffffff'}
        })

        if golyan_group:
            edges.append({
                'from': 'golyan_group',
                'to': node_id,
                'color': {'color': '#ff8844', 'opacity': 0.5},
                'width': 2,
                'dashes': [5, 5],
                'title': 'Subsidiary'
            })

    # Add lawyer
    if lawyer_name:
        nodes.append({
            'id': 'lawyer',
            'label': f'LAWYER\n{lawyer_name.split()[0]}',
            'group': 'director',
            'title': f"<b>Lawyer (Primary Controller)</b><br>{lawyer_name}<br>Controls {len(deity_companies)} companies",
            'value': 40,
            'shape': 'box',
            'font': {'size': 14, 'color': '#ffffff', 'bold': True}
        })

    # Add ALL deity companies
    for company in deity_companies.values():
        node_id = f'deity_{company.id}'
        node_id_map[company.id] = node_id

        deity = next((d for d in DEITY_NAMES if d in company.name_english.lower()), '')
        label = deity.capitalize()[:10] if deity else company.name_english[:10]

        nodes.append({
            'id': node_id,
            'label': label,
            'group': 'agro',
            'title': f"<b>{company.name_english}</b><br>Deity: {deity.capitalize()}<br>Reg: #{company.registration_number}<br>Date: {company.registration_date_bs}<br>PAN: {company.pan}",
            'value': 12,
            'font': {'size': 8, 'color': '#ffffff'}
        })

        # Connect to lawyer
        if lawyer_name:
            edges.append({
                'from': 'lawyer',
                'to': node_id,
                'color': {'color': '#44ff88', 'opacity': 0.3},
                'width': 1,
                'title': 'Controls'
            })

    # Add phone cluster connections
    for hash_val, company_ids in phone_clusters.items():
        company_ids_in_network = [cid for cid in company_ids if cid in node_id_map]
        if len(company_ids_in_network) > 1:
            # Connect all companies in cluster to each other
            for i, cid1 in enumerate(company_ids_in_network):
                for cid2 in company_ids_in_network[i+1:]:
                    edges.append({
                        'from': node_id_map[cid1],
                        'to': node_id_map[cid2],
                        'color': {'color': '#ffaa00', 'opacity': 0.4},
                        'width': 2,
                        'title': 'Shared Phone Number',
                        'dashes': [2, 2]
                    })

    # Add mobile cluster connections
    for hash_val, company_ids in mobile_clusters.items():
        company_ids_in_network = [cid for cid in company_ids if cid in node_id_map]
        if len(company_ids_in_network) > 1:
            for i, cid1 in enumerate(company_ids_in_network):
                for cid2 in company_ids_in_network[i+1:]:
                    edges.append({
                        'from': node_id_map[cid1],
                        'to': node_id_map[cid2],
                        'color': {'color': '#00aaff', 'opacity': 0.4},
                        'width': 2,
                        'title': 'Shared Mobile Number',
                        'dashes': [2, 2]
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
            min-width: 300px;
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
                <div class="legend-color" style="background: #ff8844;"></div>
                <span>Golyan Subsidiaries</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #44ff88;"></div>
                <span>Shell Companies (Agro)</span>
            </div>
            <div class="legend-item">
                <div class="legend-box" style="background: #4488ff;"></div>
                <span>Directors/Controllers</span>
            </div>
        </div>
    </div>

    <div id="controls">
        <button onclick="network.fit()">FIT VIEW</button>
        <button onclick="togglePhysics()">TOGGLE PHYSICS</button>
        <button onclick="resetZoom()">RESET</button>
    </div>

    <div id="info">
        Scroll to zoom | Drag to pan | Click nodes for details | Hover for information
    </div>

    <script type="text/javascript">
        const nodes = new vis.DataSet({json.dumps(nodes, indent=8)});

        const edges = new vis.DataSet({json.dumps(edges, indent=8)});

        const container = document.getElementById('network');
        const data = {{
            nodes: nodes,
            edges: edges
        }};

        const options = {{
            nodes: {{
                shape: 'dot',
                scaling: {{
                    min: 10,
                    max: 50
                }},
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
                    size: 10,
                    x: 0,
                    y: 0
                }}
            }},
            edges: {{
                smooth: {{
                    enabled: true,
                    type: 'continuous',
                    roundness: 0.5
                }},
                shadow: {{
                    enabled: false
                }}
            }},
            groups: {{
                parent: {{
                    color: {{
                        background: '#ff4444',
                        border: '#ffffff',
                        highlight: {{
                            background: '#ff6666',
                            border: '#ffffff'
                        }}
                    }},
                    borderWidth: 3
                }},
                golyan: {{
                    color: {{
                        background: '#ff8844',
                        border: '#ffffff',
                        highlight: {{
                            background: '#ffaa66',
                            border: '#ffffff'
                        }}
                    }},
                    borderWidth: 2
                }},
                agro: {{
                    color: {{
                        background: '#44ff88',
                        border: '#ffffff',
                        highlight: {{
                            background: '#66ffaa',
                            border: '#ffffff'
                        }}
                    }},
                    borderWidth: 1
                }},
                director: {{
                    color: {{
                        background: '#4488ff',
                        border: '#ffffff',
                        highlight: {{
                            background: '#66aaff',
                            border: '#ffffff'
                        }}
                    }},
                    borderWidth: 2
                }}
            }},
            physics: {{
                enabled: true,
                solver: 'forceAtlas2Based',
                forceAtlas2Based: {{
                    gravitationalConstant: -50,
                    centralGravity: 0.01,
                    springLength: 200,
                    springConstant: 0.08,
                    damping: 0.4,
                    avoidOverlap: 0.5
                }},
                stabilization: {{
                    enabled: true,
                    iterations: 1000,
                    updateInterval: 25
                }}
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
            network.fit({{
                animation: {{
                    duration: 1000,
                    easingFunction: 'easeInOutQuad'
                }}
            }});
        }}

        // Stabilization progress
        network.on("stabilizationProgress", function(params) {{
            const percentage = Math.round(params.iterations / params.total * 100);
            console.log('Stabilizing network: ' + percentage + '%');
        }});

        network.on("stabilizationIterationsDone", function() {{
            console.log('Network stabilized');
            network.setOptions({{ physics: false }});
        }});

        // Node click
        network.on("click", function(params) {{
            if (params.nodes.length > 0) {{
                const nodeId = params.nodes[0];
                console.log('Clicked node:', nodeId);
            }}
        }});
    </script>
</body>
</html>"""

    return html_template

async def main():
    print("Fetching complete network data...")
    data = await get_full_network_data()

    print(f"Found {len(data['deity_companies'])} shell companies (deity-themed agro)")
    print(f"Found {len(data['golyan_companies'])} Golyan companies")
    print(f"Found {len(data['phone_clusters'])} phone clusters")
    print(f"Found {len(data['mobile_clusters'])} mobile clusters")

    print("\nGenerating interactive HTML visualization...")
    html = generate_html(data)

    output_file = Path(__file__).parent.parent / "investigation_output" / "golyan_network_interactive.html"
    output_file.parent.mkdir(exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n✅ Interactive visualization generated: {output_file}")
    print(f"\nFeatures:")
    print(f"  - All {len(data['deity_companies'])} shell companies visible")
    print(f"  - All {len(data['golyan_companies'])} Golyan entities shown")
    print(f"  - Interactive: zoom, pan, drag nodes")
    print(f"  - Hover for company details")
    print(f"  - Cluster connections highlighted")
    print(f"  - Palantir-style dark theme")
    print(f"\nOpen in browser: file://{output_file}")

if __name__ == "__main__":
    asyncio.run(main())
