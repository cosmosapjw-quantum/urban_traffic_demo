"""Diagnostic figures from measured geometry and executed aggregate trajectories."""
from pathlib import Path
import json,sys


def read(path):return json.loads(Path(path).read_text())


def main(root):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    root=Path(root);out=root/'figures';out.mkdir(parents=True,exist_ok=True)
    for case in ('polycentric_river','valley_city','coastal_port'):
        d=read(root/f'area_{case}.json');p=d['boundary'];q=d['one_portal']['quadrature']
        fig,ax=plt.subplots(figsize=(9,7))
        ax.add_patch(Polygon(p,fill=False,linewidth=1.7,label='Inherited block boundary'))
        ax.scatter([r['xy'][0] for r in q],[r['xy'][1] for r in q],s=[3+400*r['weight'] for r in q],
                   alpha=.4,label='Uniform-area quadrature (not residents)')
        for name,field,marker in [('Original portal','first_gate','s'),('Proposed second portal','proposed_second_gate','^')]:
            xy=d[field]['xy'];ax.scatter([xy[0]],[xy[1]],marker=marker,s=100,label=name)
        a=d['old_anchor'];ax.scatter([a[0]],[a[1]],marker='x',s=100,label='Inherited single activity point')
        ax.annotate(f"Point proxy: {d['original_length_m']:.1f} m",xy=a,xytext=(12,20),textcoords='offset points',
                    arrowprops=dict(arrowstyle='->',lw=.7),fontsize=9)
        mean=5*d['one_portal']['mean_s'];bound=5*d['one_portal']['error_bound_s']
        ax.set(xlabel='Local x [m]',ylabel='Local y [m]',
               title=f'{case}, block {d["block"]}: area measure replaces a point proxy\n'
                     f'One-portal mean internal distance: {mean:.1f} +/- {bound:.1f} m')
        ax.autoscale();ax.set_aspect('equal');ax.margins(.12)
        ax.legend(loc='best',fontsize=8);fig.tight_layout()
        fig.savefig(out/f'area_{case}.png',dpi=150);plt.close(fig)
    d=read(root/'area_polycentric_river.json')
    fig,ax=plt.subplots(figsize=(9,5))
    for key,label,style in [('one_portal','Existing single portal','-'),('two_portal','Existing + proposed second portal','--')]:
        values=sorted((r['cost_s'],r['weight']) for r in d[key]['quadrature']);cumulative=0.;x=[];y=[]
        for cost,w in values:cumulative+=w;x.append(cost);y.append(cumulative)
        ax.step(x,y,where='post',linestyle=style,label=label)
    ax.set(xlabel='Internal access proxy time [s]',ylabel='Cumulative uniform area fraction',ylim=(0,1.03),
           title='Same block and activity measure, different physical portal set\n5 m/s planar access; no external street-time or construction-cost claim')
    ax.legend();fig.tight_layout();fig.savefig(out/'area_time_cdf.png',dpi=150);plt.close(fig)
    tr=read(root/'TRAFFIC_RESULTS.json')
    fig,ax=plt.subplots(figsize=(9,5))
    keys=['parent','parent_renamed','packet','packet_renamed'];x=list(range(4))
    ax.plot(x,[tr[k]['mean_s']['F'] for k in keys],marker='o',label='Physical population F')
    ax.plot(x,[tr[k]['mean_s']['G'] for k in keys],marker='s',linestyle='--',label='Physical population G')
    ax.set_xticks(x,['Parent','Parent, IDs swapped','Mixed packet','Mixed packet, IDs swapped'])
    ax.set(ylabel='Mean completion time [s]',title='Label renaming must not decide physical merge priority\nSame total residence conceals opposite population biases')
    ax.legend();fig.tight_layout();fig.savefig(out/'merge_label_counterexample.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,5))
    ax.plot([1,100],[tr['parent']['peak_parts'],tr['fragmented_parent']['peak_parts']],marker='o',label='Parent serial records')
    ax.plot([1,100],[tr['packet']['peak_parts'],tr['fragmented_packet']['peak_parts']],marker='s',linestyle='--',label='Additive packet representation')
    ax.set(xlabel='Input fragments per physical population',ylabel='Peak retained parts',
           title='Same 2 vehicle equivalents: representation fragmentation is not more traffic')
    ax.legend();fig.tight_layout();fig.savefig(out/'fragment_records.png',dpi=150);plt.close(fig)
    print(json.dumps({'figures':[p.name for p in sorted(out.glob('*.png'))]},indent=2))
    return list(out.glob('*.png'))

if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else 'artifacts/symmetry_observables_20261025')
