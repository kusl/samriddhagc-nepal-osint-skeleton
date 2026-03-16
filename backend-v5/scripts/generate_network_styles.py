#!/usr/bin/env python3
"""Generate multiple OSINT visualization styles for Golyan network."""
import asyncio
import sys
from pathlib import Path
from collections import defaultdict
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment, CompanyDirector

async def get_network_data():
    """Fetch all network data from database."""
    async with AsyncSessionLocal() as db:
        # Get Golyan companies
        golyan_stmt = select(CompanyRegistration).where(
            CompanyRegistration.name_english.ilike('%golyan%')
        )
        result = await db.execute(golyan_stmt)
        golyan_companies = {c.id: c for c in result.scalars().all()}

        # Get all shell companies in range
        shell_stmt = select(CompanyRegistration).where(
            and_(
                CompanyRegistration.registration_number >= 281206,
                CompanyRegistration.registration_number <= 304643,
            )
        )
        result = await db.execute(shell_stmt)
        all_companies = result.scalars().all()
        all_companies_dict = {c.id: c for c in all_companies}

        # Get IRD data for clusters
        all_entities = list(golyan_companies.values()) + list(all_companies_dict.values())
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

        # Identify clusters
        golyan_group = next((c for c in golyan_companies.values() if 'golyan group' in c.name_english.lower()), None)
        lawyer_cluster_ids = []
        ca_cluster_ids = []

        if golyan_group:
            for hash_val, company_ids in {**phone_clusters, **mobile_clusters}.items():
                if golyan_group.id in company_ids:
                    lawyer_cluster_ids = company_ids
                    break

        golyan_realty = next((c for c in golyan_companies.values() if 'realty' in c.name_english.lower()), None)
        if golyan_realty:
            for hash_val, company_ids in {**phone_clusters, **mobile_clusters}.items():
                if golyan_realty.id in company_ids:
                    ca_cluster_ids = company_ids
                    break

        # Filter shell companies
        shell_companies = {
            c.id: c for c in all_companies_dict.values()
            if c.id in (lawyer_cluster_ids + ca_cluster_ids)
            and c.name_english
            and ('agro' in c.name_english.lower() or 'forestry' in c.name_english.lower())
            and 'golyan' not in c.name_english.lower()
        }

        return {
            'shell_companies': shell_companies,
            'golyan_companies': golyan_companies,
            'lawyer_cluster_ids': lawyer_cluster_ids,
            'ca_cluster_ids': ca_cluster_ids,
            'golyan_group': golyan_group,
            'golyan_realty': golyan_realty,
        }

def generate_hierarchical_style(data):
    """Style 1: Hierarchical tree - shows organizational structure top-down."""
    shell_companies = data['shell_companies']
    golyan_companies = data['golyan_companies']
    lawyer_cluster_ids = data['lawyer_cluster_ids']
    ca_cluster_ids = data['ca_cluster_ids']
    golyan_group = data['golyan_group']

    nodes = []
    edges = []

    # Add Golyan Group at top
    if golyan_group:
        nodes.append({
            'id': 'golyan_group',
            'label': golyan_group.name_english,
            'level': 0,
            'group': 'parent',
            'title': f"<b>{golyan_group.name_english}</b><br>Reg: #{golyan_group.registration_number}<br>PAN: {golyan_group.pan}",
            'value': 80
        })

    # Add Golyan entities at level 1
    for company in golyan_companies.values():
        if company.id == (golyan_group.id if golyan_group else None):
            continue

        in_lawyer = company.id in lawyer_cluster_ids
        in_ca = company.id in ca_cluster_ids

        nodes.append({
            'id': f'gol_{company.id}',
            'label': company.name_english,
            'level': 1,
            'group': 'ca_golyan' if in_ca else 'lawyer_golyan' if in_lawyer else 'golyan',
            'title': f"<b>{company.name_english}</b><br>Cluster: {'CA' if in_ca else 'Lawyer' if in_lawyer else 'None'}",
            'value': 40
        })

        if golyan_group:
            edges.append({
                'from': 'golyan_group',
                'to': f'gol_{company.id}',
                'color': {'color': '#ff4444' if in_ca else '#44ff88' if in_lawyer else '#888'},
                'width': 3
            })

    # Add shell companies at level 2
    for company in shell_companies.values():
        in_ca = company.id in ca_cluster_ids
        in_lawyer = company.id in lawyer_cluster_ids

        nodes.append({
            'id': f'shell_{company.id}',
            'label': company.name_english[:30],
            'level': 2,
            'group': 'ca_shell' if in_ca else 'lawyer_shell',
            'title': f"<b>{company.name_english}</b><br>Reg: #{company.registration_number}",
            'value': 20
        })

        if golyan_group:
            edges.append({
                'from': 'golyan_group',
                'to': f'shell_{company.id}',
                'color': {'color': '#ff4444' if in_ca else '#44ff88'},
                'width': 1,
                'dashes': [5, 5]
            })

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Hierarchical View - Golyan Network</title>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Courier New', monospace; background: #000; color: #0f0; overflow: hidden; }}
        #header {{ background: #111; padding: 15px 25px; border-bottom: 2px solid #0f0; }}
        #header h1 {{ font-size: 20px; color: #0f0; letter-spacing: 3px; }}
        #header .subtitle {{ font-size: 11px; color: #0a0; margin-top: 5px; }}
        #network {{ width: 100%; height: calc(100vh - 100px); background: #000; }}
        #info {{ position: absolute; top: 80px; right: 20px; background: rgba(0,20,0,0.9); border: 1px solid #0f0; padding: 15px; font-size: 11px; }}
        #info h3 {{ color: #0f0; margin-bottom: 10px; border-bottom: 1px solid #0f0; padding-bottom: 5px; }}
        .legend-item {{ margin: 5px 0; display: flex; align-items: center; }}
        .legend-color {{ width: 15px; height: 15px; margin-right: 8px; border: 1px solid #0f0; }}
    </style>
</head>
<body>
    <div id="header">
        <h1>HIERARCHICAL VIEW - GOLYAN NETWORK</h1>
        <div class="subtitle">Top-Down Organizational Structure | {len(nodes)} Entities | {len(edges)} Links</div>
    </div>
    <div id="network"></div>
    <div id="info">
        <h3>LEGEND</h3>
        <div class="legend-item"><div class="legend-color" style="background: #ff4444;"></div>CA Cluster</div>
        <div class="legend-item"><div class="legend-color" style="background: #44ff88;"></div>Lawyer Cluster</div>
        <div class="legend-item"><div class="legend-color" style="background: #888;"></div>Unlinked</div>
    </div>
    <script>
        const nodes = new vis.DataSet({json.dumps(nodes, indent=4)});
        const edges = new vis.DataSet({json.dumps(edges, indent=4)});
        const container = document.getElementById('network');
        const data = {{ nodes, edges }};
        const options = {{
            layout: {{
                hierarchical: {{
                    direction: 'UD',
                    sortMethod: 'directed',
                    levelSeparation: 200,
                    nodeSpacing: 150,
                    treeSpacing: 200
                }}
            }},
            nodes: {{
                shape: 'box',
                font: {{ size: 11, face: 'Courier New', color: '#0f0' }},
                borderWidth: 2,
                shadow: true
            }},
            edges: {{
                smooth: {{ type: 'cubicBezier' }},
                arrows: {{ to: {{ enabled: true, scaleFactor: 0.5 }} }}
            }},
            groups: {{
                parent: {{ color: {{ background: '#ff4444', border: '#fff' }}, borderWidth: 3 }},
                ca_golyan: {{ color: {{ background: '#ff6666', border: '#fff' }} }},
                lawyer_golyan: {{ color: {{ background: '#66ff88', border: '#fff' }} }},
                golyan: {{ color: {{ background: '#ff8844', border: '#fff' }} }},
                ca_shell: {{ color: {{ background: '#ff9999', border: '#fff' }} }},
                lawyer_shell: {{ color: {{ background: '#88ffaa', border: '#fff' }} }}
            }},
            physics: {{ enabled: false }},
            interaction: {{ hover: true }}
        }};
        new vis.Network(container, data, options);
    </script>
</body>
</html>"""
    return html

def generate_circular_style(data):
    """Style 2: Circular cluster layout - shows clusters as separate circles."""
    shell_companies = data['shell_companies']
    golyan_companies = data['golyan_companies']
    lawyer_cluster_ids = data['lawyer_cluster_ids']
    ca_cluster_ids = data['ca_cluster_ids']
    golyan_group = data['golyan_group']

    nodes = []
    edges = []

    # Center node
    if golyan_group:
        nodes.append({
            'id': 'golyan_group',
            'label': golyan_group.name_english,
            'x': 0,
            'y': 0,
            'fixed': True,
            'group': 'parent',
            'value': 100
        })

    # Add shell companies and Golyan entities
    for company in shell_companies.values():
        in_ca = company.id in ca_cluster_ids
        nodes.append({
            'id': f'shell_{company.id}',
            'label': company.name_english[:25],
            'group': 'ca_shell' if in_ca else 'lawyer_shell',
            'value': 15
        })
        if golyan_group:
            edges.append({
                'from': 'golyan_group',
                'to': f'shell_{company.id}',
                'color': {'color': '#ff4444' if in_ca else '#44ff88'},
                'width': 2
            })

    for company in golyan_companies.values():
        if company.id == (golyan_group.id if golyan_group else None):
            continue
        nodes.append({
            'id': f'gol_{company.id}',
            'label': company.name_english,
            'group': 'golyan',
            'value': 35
        })
        if golyan_group:
            edges.append({
                'from': 'golyan_group',
                'to': f'gol_{company.id}',
                'color': {'color': '#ff8844'},
                'width': 3
            })

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Circular Layout - Golyan Network</title>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'IBM Plex Mono', monospace; background: #0a0e27; color: #fff; overflow: hidden; }}
        #header {{ background: linear-gradient(90deg, #1a1a3e, #0a0e27); padding: 15px 25px; border-bottom: 2px solid #00d9ff; }}
        #header h1 {{ font-size: 20px; color: #00d9ff; letter-spacing: 2px; text-shadow: 0 0 10px #00d9ff; }}
        #network {{ width: 100%; height: calc(100vh - 70px); background: radial-gradient(circle at center, #0a0e27, #000); }}
    </style>
</head>
<body>
    <div id="header">
        <h1>⭕ CIRCULAR CLUSTER VIEW - GOLYAN NETWORK</h1>
    </div>
    <div id="network"></div>
    <script>
        const nodes = new vis.DataSet({json.dumps(nodes, indent=4)});
        const edges = new vis.DataSet({json.dumps(edges, indent=4)});
        const container = document.getElementById('network');
        const data = {{ nodes, edges }};
        const options = {{
            layout: {{
                randomSeed: 42,
                improvedLayout: true
            }},
            nodes: {{
                shape: 'dot',
                font: {{ size: 10, color: '#fff', face: 'IBM Plex Mono' }},
                borderWidth: 2,
                shadow: {{ enabled: true, color: 'rgba(0,217,255,0.5)', size: 15 }}
            }},
            edges: {{
                smooth: {{ type: 'continuous', roundness: 0.5 }},
                width: 2
            }},
            groups: {{
                parent: {{ color: {{ background: '#00d9ff', border: '#fff' }}, borderWidth: 4 }},
                golyan: {{ color: {{ background: '#ff8844', border: '#fff' }} }},
                ca_shell: {{ color: {{ background: '#ff4466', border: '#fff' }} }},
                lawyer_shell: {{ color: {{ background: '#44ff88', border: '#fff' }} }}
            }},
            physics: {{
                enabled: true,
                solver: 'forceAtlas2Based',
                forceAtlas2Based: {{
                    gravitationalConstant: -100,
                    centralGravity: 0.01,
                    springLength: 200,
                    avoidOverlap: 1
                }},
                stabilization: {{ iterations: 2000 }}
            }},
            interaction: {{ hover: true }}
        }};
        const network = new vis.Network(container, data, options);
        network.on("stabilizationIterationsDone", () => network.setOptions({{ physics: false }}));
    </script>
</body>
</html>"""
    return html

def generate_timeline_style(data):
    """Style 3: Timeline view - shows companies by registration date."""
    shell_companies = data['shell_companies']
    golyan_companies = data['golyan_companies']
    lawyer_cluster_ids = data['lawyer_cluster_ids']
    ca_cluster_ids = data['ca_cluster_ids']

    # Sort all companies by registration number (proxy for date)
    all_companies = list(shell_companies.values()) + list(golyan_companies.values())
    sorted_companies = sorted(all_companies, key=lambda c: c.registration_number)

    nodes = []
    edges = []

    for i, company in enumerate(sorted_companies):
        is_shell = company.id in shell_companies
        in_ca = company.id in ca_cluster_ids
        in_lawyer = company.id in lawyer_cluster_ids

        node_id = f'shell_{company.id}' if is_shell else f'gol_{company.id}'

        if 'golyan group' in company.name_english.lower():
            group = 'parent'
            value = 60
        elif is_shell:
            group = 'ca_shell' if in_ca else 'lawyer_shell'
            value = 20
        else:
            group = 'golyan'
            value = 40

        nodes.append({
            'id': node_id,
            'label': f"{company.name_english[:30]}\\n#{company.registration_number}",
            'level': i,
            'group': group,
            'title': f"<b>{company.name_english}</b><br>Reg: #{company.registration_number}<br>Date: {company.registration_date_bs}<br>Cluster: {'CA' if in_ca else 'Lawyer' if in_lawyer else 'None'}",
            'value': value
        })

        # Connect to previous company
        if i > 0:
            prev_company = sorted_companies[i-1]
            prev_id = f'shell_{prev_company.id}' if prev_company.id in shell_companies else f'gol_{prev_company.id}'
            edges.append({
                'from': prev_id,
                'to': node_id,
                'color': {'color': '#ff4444' if in_ca else '#44ff88' if in_lawyer else '#888'},
                'width': 2,
                'arrows': {'to': True}
            })

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Timeline View - Golyan Network</title>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Roboto Mono', monospace; background: #1a1a1a; color: #fff; overflow: hidden; }}
        #header {{ background: #2a2a2a; padding: 15px 25px; border-bottom: 3px solid #ffaa00; }}
        #header h1 {{ font-size: 20px; color: #ffaa00; letter-spacing: 2px; }}
        #header .subtitle {{ font-size: 11px; color: #888; margin-top: 5px; }}
        #network {{ width: 100%; height: calc(100vh - 100px); background: #1a1a1a; }}
        #legend {{ position: absolute; bottom: 20px; right: 20px; background: rgba(42,42,42,0.95); border: 2px solid #ffaa00; padding: 15px; }}
        .legend-item {{ margin: 5px 0; font-size: 11px; }}
    </style>
</head>
<body>
    <div id="header">
        <h1>⏱️ TIMELINE VIEW - REGISTRATION SEQUENCE</h1>
        <div class="subtitle">Chronological order by registration number | {len(nodes)} entities</div>
    </div>
    <div id="network"></div>
    <div id="legend">
        <div class="legend-item" style="color: #44ff88;">● Lawyer Cluster</div>
        <div class="legend-item" style="color: #ff4444;">● CA Cluster</div>
        <div class="legend-item" style="color: #ffaa00;">● Golyan Group</div>
    </div>
    <script>
        const nodes = new vis.DataSet({json.dumps(nodes, indent=4)});
        const edges = new vis.DataSet({json.dumps(edges, indent=4)});
        const container = document.getElementById('network');
        const data = {{ nodes, edges }};
        const options = {{
            layout: {{
                hierarchical: {{
                    direction: 'LR',
                    sortMethod: 'directed',
                    levelSeparation: 300,
                    nodeSpacing: 80
                }}
            }},
            nodes: {{
                shape: 'box',
                font: {{ size: 10, face: 'Roboto Mono', color: '#fff' }},
                borderWidth: 2,
                margin: 10
            }},
            edges: {{
                smooth: {{ type: 'cubicBezier' }},
                arrows: {{ to: {{ scaleFactor: 0.5 }} }}
            }},
            groups: {{
                parent: {{ color: {{ background: '#ffaa00', border: '#fff' }}, borderWidth: 3 }},
                golyan: {{ color: {{ background: '#ff8844', border: '#fff' }} }},
                ca_shell: {{ color: {{ background: '#ff4466', border: '#fff' }} }},
                lawyer_shell: {{ color: {{ background: '#66ff88', border: '#fff' }} }}
            }},
            physics: {{ enabled: false }},
            interaction: {{ hover: true, zoomView: true }}
        }};
        new vis.Network(container, data, options);
    </script>
</body>
</html>"""
    return html

def generate_matrix_style(data):
    """Style 4: Matrix heatmap - shows connections as a grid."""
    shell_companies = data['shell_companies']
    golyan_companies = data['golyan_companies']
    lawyer_cluster_ids = data['lawyer_cluster_ids']
    ca_cluster_ids = data['ca_cluster_ids']

    all_companies = list(golyan_companies.values()) + list(shell_companies.values())

    # Create matrix data
    matrix_data = []
    for company in all_companies:
        in_lawyer = company.id in lawyer_cluster_ids
        in_ca = company.id in ca_cluster_ids
        is_golyan = company.id in golyan_companies

        matrix_data.append({
            'name': company.name_english,
            'reg': company.registration_number,
            'cluster': 'Lawyer' if in_lawyer else 'CA' if in_ca else 'None',
            'type': 'Golyan Entity' if is_golyan else 'Shell Company'
        })

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Matrix View - Golyan Network</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Consolas', monospace; background: #000; color: #0f0; padding: 20px; }}
        h1 {{ color: #0f0; text-align: center; margin-bottom: 20px; letter-spacing: 3px; font-size: 24px; }}
        .matrix-container {{ overflow-x: auto; max-height: 90vh; }}
        table {{ border-collapse: collapse; width: 100%; background: #001a00; }}
        th {{ background: #003300; color: #0f0; padding: 12px; border: 1px solid #0f0; position: sticky; top: 0; }}
        td {{ padding: 10px; border: 1px solid #003300; font-size: 11px; }}
        .lawyer {{ background: rgba(68, 255, 136, 0.2); }}
        .ca {{ background: rgba(255, 68, 68, 0.2); }}
        .golyan-entity {{ font-weight: bold; color: #ff8844; }}
        .shell {{ color: #0f0; }}
        tr:hover {{ background: rgba(0, 255, 0, 0.1); }}
    </style>
</head>
<body>
    <h1>█ MATRIX VIEW - GOLYAN NETWORK █</h1>
    <div class="matrix-container">
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Company Name</th>
                    <th>Reg #</th>
                    <th>Type</th>
                    <th>Cluster</th>
                </tr>
            </thead>
            <tbody>"""

    for i, item in enumerate(matrix_data, 1):
        cluster_class = 'lawyer' if item['cluster'] == 'Lawyer' else 'ca' if item['cluster'] == 'CA' else ''
        type_class = 'golyan-entity' if item['type'] == 'Golyan Entity' else 'shell'
        html += f"""
                <tr class="{cluster_class}">
                    <td>{i}</td>
                    <td class="{type_class}">{item['name']}</td>
                    <td>#{item['reg']}</td>
                    <td>{item['type']}</td>
                    <td><strong>{item['cluster']}</strong></td>
                </tr>"""

    html += f"""
            </tbody>
        </table>
    </div>
    <div style="margin-top: 20px; text-align: center; font-size: 12px; color: #0a0;">
        Total Entities: {len(matrix_data)} | Lawyer Cluster: {len(lawyer_cluster_ids)} | CA Cluster: {len(ca_cluster_ids)}
    </div>
</body>
</html>"""
    return html

async def main():
    print("Generating multiple OSINT visualization styles...")
    data = await get_network_data()

    output_dir = Path(__file__).parent.parent / "investigation_output"
    output_dir.mkdir(exist_ok=True)

    styles = {
        'golyan_network_hierarchical.html': ('Hierarchical Tree', generate_hierarchical_style),
        'golyan_network_circular.html': ('Circular Cluster', generate_circular_style),
        'golyan_network_timeline.html': ('Timeline Sequence', generate_timeline_style),
        'golyan_network_matrix.html': ('Matrix Grid', generate_matrix_style),
    }

    for filename, (style_name, generator_func) in styles.items():
        print(f"  Creating {style_name}...")
        html = generator_func(data)
        output_file = output_dir / filename
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"    ✅ {output_file}")

    print(f"\n✅ Generated {len(styles)} different OSINT visualization styles!")
    print("\nStyles created:")
    print("  1. Hierarchical Tree - Top-down organizational structure")
    print("  2. Circular Cluster - Radial cluster visualization")
    print("  3. Timeline Sequence - Chronological registration order")
    print("  4. Matrix Grid - Tabular data view")

if __name__ == "__main__":
    asyncio.run(main())
