"""Diagnostic views of saved executed map/transport outputs; not solver inputs."""
from pathlib import Path
import json,sys


def main(root,show=False):
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Rectangle
    root=Path(root);out=root/'figures';out.mkdir(parents=True,exist_ok=True)
    for style in ('organic','ring_radial'):
        data=json.loads((root/f'map_{style}.json').read_text());final=data['history'][-1]
        city=final['city'];epoch_by={x['site']:i+1 for i,e in enumerate(data['epochs']) for x in e['built']}
        fig,ax=plt.subplots(figsize=(10,8))
        old=[s for s in city['sections'] if not s['id'].startswith('access:')]
        ax.add_collection(LineCollection([[p[:2] for p in s['points']] for s in old],linewidths=.45,label='Existing road structure'))
        for epoch,ls in ((1,'solid'),(2,'dashed'),(3,'dotted')):
            secs=[s for s in city['sections'] if s['id'].startswith('access:') and epoch_by[s['id'][7:]]==epoch]
            ax.add_collection(LineCollection([[p[:2] for p in s['points']] for s in secs],linewidths=3,linestyles=ls,label=f'New access, epoch {epoch}'))
        for p in final['plots']:
            r=p['footprint'];x=(r['xmin']+r['xmax'])/2;y=(r['ymin']+r['ymax'])/2
            ax.add_patch(Rectangle((r['xmin'],r['ymin']),r['xmax']-r['xmin'],r['ymax']-r['ymin'],fill=False,lw=1.))
            ax.scatter([x],[y],marker='o' if p['residents'] else 'x',s=35)
            ax.annotate(f"{p['residents']}/95",(x,y),xytext=(5,8),textcoords='offset points',fontsize=8)
        t=city['terrain'];L=t['n']*t['spacing_m']
        for r in t['water']+t['protected']:
            ax.add_patch(Rectangle((r['xmin'],r['ymin']),r['xmax']-r['xmin'],r['ymax']-r['ymin'],fill=False,hatch='//',alpha=.3))
        ax.set(xlim=(0,L),ylim=(0,L),xlabel='x [m]',ylabel='y [m]',
               title=f'{style}: physical access unlocks incremental development\n360 new residents; 4 occupied sites; {data["built_m"]:.1f} m added')
        ax.set_aspect('equal');ax.legend(fontsize=8,loc='lower left');fig.tight_layout()
        fig.savefig(out/f'development_{style}.png',dpi=150)
        if show and style=='organic':plt.show()
        plt.close(fig)
    data=json.loads((root/'TRAFFIC_RESULTS.json').read_text())
    rows=[dict(time_s=0.,progress_m=0.)]+data['ordered']['trace']
    entryZ=next(r['progress_m'] for r in rows if r['time_s']==10.)
    fig,ax=plt.subplots(figsize=(9,5))
    ax.plot([r['time_s'] for r in rows],[min(100.,r['progress_m']) for r in rows],label='Early batch enters at 0 s')
    late=[r for r in rows if r['time_s']>=10.]
    ax.plot([r['time_s'] for r in late],[min(100.,r['progress_m']-entryZ) for r in late],'--',label='Late batch enters at 10 s')
    ax.set(xlim=(0,26),xlabel='Time [s]',ylabel='Distance along lane [m]',
           title='One shared motion clock prevents within-link overtaking\nEndpoint service is modeled separately in FIFO order')
    ax.legend();fig.tight_layout();fig.savefig(out/'common_clock.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,5))
    for case in data['growing_modes']:
        r=case['trace'];ax.semilogy([x['time_s'] for x in r],[x['mode_amplitude'] for x in r],label=f'dt={case["dt_s"]} s; growth={case["observed_per_s"]:.5f}/s')
    ax.set(xlabel='Time [s]',ylabel='Headway Fourier amplitude [m]',
           title='A growing mode is retained, not artificially suppressed\n32-state periodic motif; safety limiter inactive in this experiment')
    ax.legend();fig.tight_layout();fig.savefig(out/'ring_growing_mode.png',dpi=150);plt.close(fig)
    m=json.loads((root/'map_organic.json').read_text())
    fig,ax=plt.subplots(figsize=(8,5))
    ax.step([0]+[r['epoch'] for r in m['epochs']],[0]+[r['residents'] for r in m['epochs']],where='post',label='Residents in physically served sites')
    ax.plot([0]+[r['epoch'] for r in m['epochs']],[0]+[r['offered'] for r in m['epochs']],'--',label='Cumulative new population')
    ax.set(xlabel='Slow development epoch',ylabel='Persons',title='Incremental population ledger; existing 100k stock held fixed')
    ax.legend();fig.tight_layout();fig.savefig(out/'development_ledger.png',dpi=150);plt.close(fig)
    return [str(p) for p in sorted(out.glob('*.png'))]

if __name__=='__main__':
    print('\n'.join(main(Path(sys.argv[1]) if len(sys.argv)>1 else Path('artifacts/access_fifo_20261025'))))
