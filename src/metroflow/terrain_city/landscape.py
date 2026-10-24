"""Synthetic polygon landscapes with explicit metre geometry.

The bilinear height raster is authoritative terrain, polygon masks authoritative
water/protection. No hydrologic erosion, cadastral or surveyed-city claim.
"""
from dataclasses import dataclass, field
import math
from ..environment.terrain import Terrain
from ..restored_geometry import crossing

@dataclass(frozen=True, slots=True)
class Polygon:
    name: str
    points: tuple[tuple[float,float], ...]
    bounds: tuple[float,float,float,float] = field(init=False)

    def __post_init__(self):
        if len(self.points)<3 or any(len(p)!=2 or not all(map(math.isfinite,p)) for p in self.points):
            raise ValueError('finite polygon vertices required')
        object.__setattr__(self,'bounds',(min(p[0] for p in self.points),min(p[1] for p in self.points),
                                        max(p[0] for p in self.points),max(p[1] for p in self.points)))

@dataclass(frozen=True, slots=True)
class Landscape:
    kind: str
    seed: int
    terrain: Terrain
    water: tuple[Polygon,...]
    protected: tuple[Polygon,...]

    @property
    def size_m(self):return self.terrain.n*self.terrain.spacing_m


def edges(points):return zip(points,points[1:]+points[:1])

def point_segment(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1];den=dx*dx+dy*dy
    u=0. if den==0 else max(0.,min(1.,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den))
    return math.hypot(p[0]-a[0]-u*dx,p[1]-a[1]-u*dy)

def inside(p,region):
    x,y=p;x0,y0,x1,y1=region.bounds
    if x<x0 or x>x1 or y<y0 or y>y1:return False
    hit=False
    for a,b in edges(region.points):
        if point_segment(p,a,b)<1e-8:return True
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:hit=not hit
    return hit


def segment_clear(a,b,regions,half_width=0.):
    """Exact closed-segment / polygon distance in xy, including road half-width."""
    if not math.isfinite(half_width) or half_width<0:raise ValueError('invalid footprint width')
    x0=min(a[0],b[0])-half_width;y0=min(a[1],b[1])-half_width
    x1=max(a[0],b[0])+half_width;y1=max(a[1],b[1])+half_width
    for r in regions:
        l,d,u,t=r.bounds
        if x1<l or u<x0 or y1<d or t<y0:continue
        if inside(a,r) or inside(b,r):return False
        for c,d in edges(r.points):
            if crossing(a,b,c,d) is not None:return False
            if half_width and min(point_segment(a,c,d),point_segment(b,c,d),
                                  point_segment(c,a,b),point_segment(d,a,b))<=half_width:return False
    return True


def polygon_clear(points,regions):
    """Conservative whole-block exclusion, including an obstacle wholly inside."""
    if any(not segment_clear(a,b,regions) for a,b in edges(points)):return False
    poly=Polygon('query',tuple(points))
    return not any(inside(r.points[0],poly) for r in regions)


def _ellipse(name,cx,cy,rx,ry,angle=0.):
    ca,sa=math.cos(angle),math.sin(angle)
    return Polygon(name,tuple((cx+ca*rx*math.cos(k*math.pi/16)-sa*ry*math.sin(k*math.pi/16),
                              cy+sa*rx*math.cos(k*math.pi/16)+ca*ry*math.sin(k*math.pi/16)) for k in range(32)))


def make_landscape(kind='river',size_m=8000.,seed=17):
    if kind not in ('flat','river','coast','valley','lake') or not math.isfinite(size_m) or size_m<1000:
        raise ValueError('supported landscape and size>=1000m required')
    if isinstance(seed,bool) or not isinstance(seed,int):raise ValueError('integer seed required')
    L=size_m;vertical=L/8000.;phase=(seed%23)/23*2*math.pi
    river=lambda y:.48*L+.065*L*math.sin(2*math.pi*y/L+.4)+.022*L*math.sin(4*math.pi*y/L+phase)
    valley=lambda x:.48*L+.12*L*math.sin(1.6*math.pi*x/L-.5)
    shore=lambda y:.22*L+.065*L*math.sin(2*math.pi*y/L+.5)+.025*L*math.sin(5*math.pi*y/L)
    water=[]
    if kind=='river':
        ys=tuple(-100.+(L+200.)*k/80 for k in range(81))
        water=[Polygon('river',tuple((river(y)-(.010+.003*math.cos(y/L*6))*L,y) for y in ys)+
                               tuple((river(y)+(.010+.003*math.cos(y/L*6))*L,y) for y in reversed(ys)))]
    elif kind=='valley':
        xs=tuple(-100.+(L+200.)*k/80 for k in range(81))
        water=[Polygon('valley_river',tuple((x,valley(x)-.007*L) for x in xs)+
                               tuple((x,valley(x)+.007*L) for x in reversed(xs)))]
    elif kind=='coast':
        ys=tuple(-100.+(L+200.)*k/80 for k in range(81))
        water=[Polygon('sea',((-100.,-100.),)+tuple((shore(y),y) for y in ys)+((-100.,L+100.),))]
    elif kind=='lake':water=[_ellipse('lake',.51*L,.54*L,.105*L,.15*L,.4)]
    protected=(_ellipse('reserve',.83*L,.81*L,.10*L,.12*L,.2),)
    if kind=='valley':protected=(_ellipse('reserve',.78*L,.80*L,.14*L,.09*L,-.3),)
    def z(x,y):
        base=20.+.001*x+.002*y+4*vertical*math.sin(2*math.pi*x/L)*math.sin(2*math.pi*y/L)
        if kind=='flat':return base
        if kind=='river':return base+130*vertical*math.exp(-((x-.79*L)**2+(y-.73*L)**2)/(2*(.14*L)**2))
        if kind=='coast':return base+180*vertical*((x-shore(y))/L)**2+240*vertical*math.exp(-((x-.84*L)**2+(y-.77*L)**2)/(2*(.14*L)**2))
        if kind=='valley':return base+620*vertical*((y-valley(x))/(.52*L))**2+45*vertical*math.exp(-((x-.42*L)/(.1*L))**2)
        return base+220*vertical*math.exp(-((x-.78*L)**2+(y-.78*L)**2)/(2*(.18*L)**2))
    n=64;terrain=Terrain(n,L/n,tuple(z(i*L/n,j*L/n) for j in range(n+1) for i in range(n+1)))
    return Landscape(kind,seed,terrain,tuple(water),protected)
