"""Render executed JSON evidence; plotting dependencies never enter the solver."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metroflow.restored_city import RoadMap,Junction,Section
from metroflow.environment.terrain import Terrain,Rect
from render_restored_city import draw


def read(path):
    return json.loads(Path(path).read_text())


def roadmap(data):
    t=data['terrain']
    terrain=Terrain(t['n'],t['spacing_m'],tuple(t['heights_m']),
                    tuple(Rect(**r) for r in t['water']),tuple(Rect(**r) for r in t['protected']),
                    tuple(t['bridge_rows']))
    nodes=tuple(Junction(n['id'],tuple(n['xyz']),n['layer']) for n in data['nodes'])
    sections=tuple(Section(**(s|{'points':tuple(tuple(p) for p in s['points'])})) for s in data['sections'])
    return RoadMap(data['style'],terrain,nodes,sections,tuple(tuple(x) for x in data['rejected']))


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    root=Path(sys.argv[1]) if len(sys.argv)>1 else Path('artifacts/restored_layers_20261024/resume')
    out=root/'figures';out.mkdir(parents=True,exist_ok=True)
    for style in ('grid_core','organic','superblock_mixed','ring_radial'):
        data=read(root/f'input_{style}_baseline_300s.json')
        label='organic (warped-grid control)' if style=='organic' else style
        draw(roadmap(data['map']),out/f'{style}.png',f'{label}: regenerated physical road authority')
    baseline=read(root/'traffic_grid_core_baseline_600s.json')
    closure=read(root/'traffic_grid_core_bridge_closed_600s.json')
    fig,ax=plt.subplots(figsize=(9,5))
    for name,data in (('Baseline',baseline),('Bridge group closed, 60–180 s',closure)):
        ax.plot([r['time_s'] for r in data['trace']], [r['completed'] for r in data['trace']],label=name)
    ax.set(xlabel='Time [s]',ylabel='Completed vehicle equivalents',
           title='Matched demand: 100,000 residents, 961.927 vehicles released by 600 s')
    ax.legend();fig.tight_layout();fig.savefig(out/'matched_bridge_completion.png',dpi=140);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,5))
    for key in ('released','completed','active','pending'):
        ax.plot([r['time_s'] for r in closure['trace']],[r[key] for r in closure['trace']],label=key)
    ax.set(xlabel='Time [s]',ylabel='Vehicle equivalents',title='Bridge closure: released = completed + active + pending')
    ax.legend();fig.tight_layout();fig.savefig(out/'traffic_mass_ledger.png',dpi=140);plt.close(fig)
    data=read(root/'input_grid_core_bridge_closed_600s.json')
    city=roadmap(data['map']);rd={r['id']:r for r in data['compiled']['roads']}
    snap=min(closure['snapshots'],key=lambda s:abs(s['time_s']-120.))
    masses=dict(zip(closure['road_ids'],snap['occupancy_veh']))
    occupancy={};storage={}
    for b in data['compiled']['crosswalk']:
        k=b['section_id'];i=b['link_id']
        occupancy[k]=occupancy.get(k,0.)+masses[i]
        storage[k]=storage.get(k,0.)+rd[i]['storage_veh']
    fig,ax=plt.subplots(figsize=(10,9))
    for facility,linestyle in (('surface','solid'),('bridge','dashdot'),('mainline','dashed'),('ramp','dotted')):
        sections=[s for s in city.sections if s.facility==facility]
        ax.add_collection(LineCollection([[p[:2] for p in s.points] for s in sections],
             linewidths=[.5+5*occupancy[s.id]/storage[s.id] for s in sections],
             linestyles=linestyle,label=facility))
    for s in city.sections:
        if s.failure_group=='bridge:6':
            middle=s.points[len(s.points)//2]
            ax.annotate('Both directions closed',xy=middle[:2],xytext=(2600,3300),
                        arrowprops=dict(arrowstyle='->'))
    L=city.terrain.n*city.terrain.spacing_m
    ax.set(xlim=(0,L),ylim=(0,L),xlabel='x [m]',ylabel='y [m]',
           title='Occupancy / directional storage at 120 s; width shows load, not road width')
    ax.set_aspect('equal');ax.legend();fig.tight_layout();fig.savefig(out/'traffic_occupancy_120s.png',dpi=140);plt.close(fig)
    rows=[]
    for suffix in ('','_dt2.5','_dt1.25'):
        r=read(root/f'traffic_grid_core_baseline_300s{suffix}.json')
        rows.append((5. if not suffix else float(suffix[3:]),r['completed'],r['peak_arrival_records']))
    for index,label,name in ((1,'Completed vehicle equivalents at 300 s','dt_completion'),
                            (2,'Peak aggregate arrival records','dt_arrivals')):
        fig,ax=plt.subplots(figsize=(8,5));ax.plot([r[0] for r in rows],[r[index] for r in rows],marker='o')
        ax.set(xlabel='Time step [s]',ylabel=label,title='Matched-input time refinement; not a convergence certificate')
        fig.tight_layout();fig.savefig(out/f'{name}.png',dpi=140);plt.close(fig)
    print(json.dumps({'figures':[p.name for p in sorted(out.glob('*.png'))]},indent=2))

if __name__=='__main__':main()
