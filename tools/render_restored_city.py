"""Diagnostic plots only; metre coordinates and physical polyline authority."""
from pathlib import Path
import sys,json
from dataclasses import asdict
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metroflow.restored_city import generate,STYLES
from metroflow.restored_geometry import crossing_audit,components


def draw(city,path,title=None):
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Rectangle
    fig,ax=plt.subplots(figsize=(11,9))
    t=city.terrain
    xs=[i*t.spacing_m for i in range(t.n+1)]
    hs=[t.heights_m[j*(t.n+1):(j+1)*(t.n+1)] for j in range(t.n+1)]
    cs=ax.contour(xs,xs,hs,levels=8,linewidths=.45,alpha=.5)
    ax.clabel(cs,inline=True,fontsize=7,fmt='%g m')
    for group,hatch,label in ((t.water,'///','Water exclusion'),(t.protected,'xx','Protected land')):
        for k,r in enumerate(group):
            ax.add_patch(Rectangle((r.xmin,r.ymin),r.xmax-r.xmin,r.ymax-r.ymin,
                fill=False,hatch=hatch,alpha=.35,label=label if k==0 else None))
    for hierarchy,width in (('local',.6),('collector',1.),('arterial',1.8),('expressway',2.3)):
        vals=[s for s in city.sections if s.hierarchy==hierarchy and s.facility not in ('bridge','ramp')]
        ax.add_collection(LineCollection([[p[:2] for p in s.points] for s in vals],linewidths=width,
            linestyles='dashed' if hierarchy=='expressway' else 'solid',label=hierarchy))
    for fac,line,width in (('bridge','dashdot',2.6),('ramp','dotted',2.5)):
        vals=[s for s in city.sections if s.facility==fac]
        ax.add_collection(LineCollection([[p[:2] for p in s.points] for s in vals],linewidths=width,
            linestyles=line,label=fac))
        if fac=='ramp':
            for s in vals:
                a,b=s.points[0],s.points[-1]
                p=(a[0]+.45*(b[0]-a[0]),a[1]+.45*(b[1]-a[1]))
                q=(a[0]+.65*(b[0]-a[0]),a[1]+.65*(b[1]-a[1]))
                ax.annotate('',xy=q,xytext=p,arrowprops=dict(arrowstyle='->',lw=1.))
    # Only actual endpoint incidence yields a dot. Projected flyovers do not.
    ax.scatter([n.xyz[0] for n in city.nodes if n.layer==0],
               [n.xyz[1] for n in city.nodes if n.layer==0],s=3,marker='.')
    L=t.n*t.spacing_m
    ax.set(xlim=(0,L),ylim=(0,L),xlabel='x [m]',ylabel='y [m]',
           title=title or f'{city.style}: physical hierarchy, bridges, directed ramps')
    ax.set_aspect('equal');ax.legend(fontsize=8,loc='upper left');fig.tight_layout()
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(path,dpi=140);plt.close(fig)


def main():
    out=Path(sys.argv[1]) if len(sys.argv)>1 else Path('artifacts/restored_layers_20261024/maps')
    out.mkdir(parents=True,exist_ok=True);reports={}
    for style in STYLES:
        city=generate(style);a=crossing_audit(city)
        reports[style]=dict(nodes=len(city.nodes),roads=len(city.sections),
            components=len(set(components(city).values())),rejected=dict(city.rejected),audit=a)
        (out/f'{style}.json').write_text(json.dumps(asdict(city),indent=2,allow_nan=False))
        draw(city,out/f'{style}.png')
    (out/'audit.json').write_text(json.dumps(reports,indent=2))
    print(json.dumps({s:{k:v for k,v in r.items() if k!='audit'}|
          dict(illegal_crossings=len(r['audit']['illegal'])) for s,r in reports.items()},indent=2))

if __name__=='__main__':main()
