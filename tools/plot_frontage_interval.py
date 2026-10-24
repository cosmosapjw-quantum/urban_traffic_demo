"""Render saved map/clock/ablation evidence; plotting is not in the solver."""
from pathlib import Path
import sys,json

def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Rectangle
    root=Path(sys.argv[1]) if len(sys.argv)>1 else Path('artifacts/frontage_interval_20261024')
    out=root/'figures';out.mkdir(parents=True,exist_ok=True)
    load=lambda p:json.loads(p.read_text())
    for style in ('organic','ring_radial'):
        data=load(root/'map'/f'{style}.json');city=data['after'];terrain=city['terrain']
        fig,ax=plt.subplots(figsize=(11,9));old=[];added=[];upper=[]
        for s in city['sections']:
            points=[p[:2] for p in s['points']]
            (added if s['id'].startswith('access:') else upper if s['facility']=='mainline' else old).append(points)
        ax.add_collection(LineCollection(old,linewidths=.65,label='Existing ground roads and ramps'))
        ax.add_collection(LineCollection(upper,linewidths=1.2,linestyles='dashdot',label='Elevated mainlines'))
        ax.add_collection(LineCollection(added,linewidths=2.4,linestyles='dashed',label='New physical access roads'))
        for key,hatch,label in (('water','///','Water'),('protected','xx','Protected land')):
            for i,r in enumerate(terrain[key]):
                ax.add_patch(Rectangle((r['xmin'],r['ymin']),r['xmax']-r['xmin'],r['ymax']-r['ymin'],
                                     fill=False,hatch=hatch,alpha=.3,label=label if i==0 else None))
        ax.scatter([s['xy'][0] for s in data['sites']],[s['xy'][1] for s in data['sites']],marker='x',s=28,label='Declared activity sites')
        limit=terrain['n']*terrain['spacing_m'];ax.set(xlim=(0,limit),ylim=(0,limit),xlabel='x [m]',ylabel='y [m]')
        ax.set_aspect('equal');ax.set_title(f'{style}: physical frontage, not zero-cost access\n{data["result"]["used_length_m"]:.2f} m used out of 900 m budget')
        ax.legend(fontsize=8);fig.tight_layout();fig.savefig(out/f'{style}_access.png',dpi=150);plt.close(fig)
    data=load(root/'final_oracles/oracles.json')
    fig,ax=plt.subplots(figsize=(9,5))
    for key,label,marker in (('Model','Legacy','o'),('PackedModel','Packed causal grid','s'),('IntervalModel','Interval reference','^')):
        rows=sorted((r for r in data if r['model']==key),key=lambda x:x['dt_s'])
        ax.plot([r['dt_s'] for r in rows],[r['mean_s'] for r in rows],marker=marker,label=label)
    ax.axhline(10.,linestyle='dotted',label='Exact 10 s')
    ax.set(xlabel='Step / bulk-update period [s]',ylabel='Mean completed travel time [s]',title='Frozen, uncongested single-link oracle')
    ax.legend();fig.tight_layout();fig.savefig(out/'freeflow_clock.png',dpi=150);plt.close(fig)
    data=load(root/'packed/compression_ablation.json')
    fig,ax=plt.subplots(figsize=(8,5))
    ax.bar(['Point calendar\n(same corrected clock)','Packed runs'],[data['point_records'],data['packed_records']],hatch='/')
    ax.set(ylabel='Peak aggregate arrival records',title='Matched-clock city ablation: no change to demand or physics')
    for i,v in enumerate((data['point_records'],data['packed_records'])):ax.text(i,v+80,str(v),ha='center')
    ax.set_ylim(0,data['point_records']*1.18);fig.tight_layout();fig.savefig(out/'calendar_ablation.png',dpi=150);plt.close(fig)
    print('\n'.join(str(p) for p in sorted(out.glob('*.png'))))

if __name__=='__main__':main()
