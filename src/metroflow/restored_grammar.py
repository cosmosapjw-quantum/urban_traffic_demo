"""Small explicit ports of original morphology/ramp semantics.

Not a byte port of scalable_synthetic_v2; no public default is changed.
"""
import math
from collections import Counter
from .environment.terrain import synthetic_terrain
from .restored_geometry import elevation,ground_profile,deck_profile,terrain_gate,minimum_ground_gap


def build(style,n=12,seed=17,interchanges=True):
    from .restored_city import STYLES,Junction,Section,RoadMap
    if style not in STYLES:raise ValueError('unsupported restored style')
    terrain=synthetic_terrain(n=n,seed=seed);extent=n*terrain.spacing_m
    nodes={};sections=[];rejected=Counter();grid={}
    lanes={'local':(1,1),'collector':(1,1),'arterial':(2,2),'expressway':(2,0)}
    def vertex(key,xy,layer=0,z=None):
        xyz=(*xy,elevation(terrain,*xy) if z is None else z)
        node=Junction(key,xyz,layer)
        if key in nodes and nodes[key]!=node:raise ValueError('inconsistent shared junction')
        nodes[key]=node
        return key
    def add(key,u,v,xy,hierarchy='local',facility='surface',deck=None,group=None,role=None):
        counts=(1,0) if facility=='ramp' else lanes[hierarchy]
        width=3.5*sum(counts)+2.
        reason=terrain_gate(terrain,xy,width,facility)
        if reason:rejected[reason]+=1;return False
        try:points,length,grade=ground_profile(terrain,xy) if deck is None else deck_profile(deck)
        except ValueError:rejected['outside_terrain']+=1;return False
        if grade>.12:rejected['grade']+=1;return False
        if deck is not None and minimum_ground_gap(terrain,points)<-1e-8:
            rejected['buried_deck']+=1;return False
        if points[0]!=nodes[u].xyz or points[-1]!=nodes[v].xyz:
            raise ValueError('endpoint geometry mismatch')
        sections.append(Section(key,u,v,points,hierarchy,facility,*counts,length,grade,group,role));return True
    phase=(seed%19)/19*2*math.pi
    def warp(x,y):
        if style!='organic':return x,y
        # Bounded smooth, locally curvilinear lattice embedding, not organic topology.
        a=.024*extent
        return (x+a*math.sin(math.pi*x/extent)*math.sin(2*math.pi*y/extent+phase),
                y+a*math.sin(2*math.pi*x/extent+phase)*math.sin(math.pi*y/extent))
    if style!='ring_radial':
        for y in range(1,n):
            for x in range(1,n):
                xy=warp(x*terrain.spacing_m,y*terrain.spacing_m)
                if terrain_gate(terrain,(xy,xy),12.,'surface'):continue
                key=vertex(f's{x}:{y}',xy);grid[x,y]=key
        for (x,y),u in sorted(grid.items()):
            for xx,yy in ((x+1,y),(x,y+1)):
                if (xx,yy) not in grid:continue
                if style=='superblock_mixed' and ((x%3==1 and y%3==1 and yy==y) or
                                                (x%3==2 and y%3==2 and xx==x)):continue
                v=grid[xx,yy];along=y if yy==y else x
                hierarchy='arterial' if along%4==0 else 'collector' if along%3==0 else 'local'
                xy=tuple(warp((x+(xx-x)*k/4)*terrain.spacing_m,
                              (y+(yy-y)*k/4)*terrain.spacing_m) for k in range(5))
                add(f'grid:{u}>{v}',u,v,xy,hierarchy)
        for row in (n//3,n//2,2*n//3):
            candidates=[(x,key) for (x,y),key in grid.items() if y==row]
            left=[r for r in candidates if r[0]<n/2];right=[r for r in candidates if r[0]>n/2]
            if left and right:
                u=max(left)[1];v=min(right)[1];_bridge(add,nodes,terrain,u,v,f'bridge:{row}')
    else:
        # Two bank-centred ring/radial precincts: no artificial degree-16 hub.
        for bank,cx in enumerate((.24*extent,.76*extent)):
            cy=.5*extent
            for ring,radius in enumerate((.055*extent,.105*extent,.16*extent,.22*extent)):
                for j in range(16):
                    angle=j*math.pi/8;xy=(cx+radius*math.cos(angle),cy+radius*math.sin(angle))
                    vertex(f'r{bank}:{ring}:{j}',xy)
                for j in range(16):
                    u=f'r{bank}:{ring}:{j}';v=f'r{bank}:{ring}:{(j+1)%16}'
                    xy=tuple((cx+radius*math.cos((j+k/4)*math.pi/8),
                              cy+radius*math.sin((j+k/4)*math.pi/8)) for k in range(5))
                    # Ensure periodic endpoint uses the same floating representation.
                    xy=(nodes[u].xyz[:2],*xy[1:-1],nodes[v].xyz[:2])
                    add(f'arc:{u}>{v}',u,v,xy,'arterial' if ring==2 else 'local')
                    if ring and (j%2==0 or ring<3):
                        a=f'r{bank}:{ring-1}:{j}'
                        add(f'spoke:{a}>{u}',a,u,(nodes[a].xyz[:2],nodes[u].xyz[:2]),
                            'collector' if j%4==0 else 'local')
        for j,k in ((2,6),(0,8),(14,10)):
            _bridge(add,nodes,terrain,f'r0:3:{j}',f'r1:3:{k}',f'bridge:{j}')
    if interchanges:
        _expressway(vertex,add,nodes,sections,terrain)
    used={p for s in sections for p in (s.start,s.end)}
    # Unused proposal nodes are not developed city junctions; rejection counts survive.
    return RoadMap(style,terrain,tuple(nodes[k] for k in sorted(used)),tuple(sections),tuple(sorted(rejected.items())))


def _bridge(add,nodes,t,u,v,group):
    a,b=nodes[u].xyz,nodes[v].xyz
    # Follow the bank-to-bank grade plus an 8m smooth crown. No discontinuous
    # high-bank horizontal deck whose short abutment exceeds the grade limit.
    points=tuple((a[0]+u*(b[0]-a[0]),a[1]+u*(b[1]-a[1]),
                  a[2]+u*(b[2]-a[2])+8.*math.sin(math.pi*u)) for u in (0.,.25,.5,.75,1.))
    points=(a,*points[1:-1],b)

    add(group,u,v,tuple(p[:2] for p in points),'arterial','bridge',points,group)


def _expressway(vertex,add,nodes,sections,t):
    from .restored_city import RoadMap
    from .restored_geometry import crossing_audit
    L=t.n*t.spacing_m
    xs=(.10,.24,.36,.64,.76,.90);ys=(.42*L-12.,.42*L+12.)
    deck=max(elevation(t,L*x,y) for y in ys for x in (k/100 for k in range(10,91)))+10.
    surface={p for s in sections if s.facility=='surface' for p in (s.start,s.end)}
    carriageways=[]
    # Both carriageways are fixed before any ramp is proposed or audited.
    for direction,y in enumerate(ys):
        keys=[vertex(f'h{direction}:{i}',(x*L,y),1,deck) for i,x in enumerate(xs)]
        carriageways.append(keys)
        for i in (range(5) if direction==0 else range(4,-1,-1)):
            u,v=(keys[i],keys[i+1]) if direction==0 else (keys[i+1],keys[i])
            pts=(nodes[u].xyz,nodes[v].xyz)
            group='highway_river' if i==2 else f'highway:{direction}:{i}'
            add(f'main:{direction}:{i}',u,v,tuple(p[:2] for p in pts),'expressway','mainline',pts,group)
    for direction,y in enumerate(ys):
        keys=carriageways[direction]
        for idx,role in ((1,'on_ramp'),(2,'off_ramp'),(3,'on_ramp'),(4,'off_ramp')):
            if direction:role='off_ramp' if role=='on_ramp' else 'on_ramp'
            highway=keys[idx];hx=xs[idx]*L
            dx=-.07*L if (role=='on_ramp')==(direction==0) else .07*L
            target=(hx+dx,(.27 if direction==0 else .57)*L)
            candidates=sorted((s for s in surface if
                (nodes[s].xyz[1]<y-200 if direction==0 else nodes[s].xyz[1]>y+200)),
                key=lambda s:(math.dist(nodes[s].xyz[:2],target),s))
            for surf in candidates[:12]:
                u,v=(surf,highway) if role=='on_ramp' else (highway,surf)
                a,b=nodes[u].xyz,nodes[v].xyz
                if math.dist(a[:2],b[:2])<200.:continue
                sign=1 if direction==0 else -1
                if sign*(b[0]-a[0])<=80.:continue
                pts=_ramp_curve(a,b,sign,role)
                key=f'{role}:{direction}:{idx}'
                if not add(key,u,v,tuple(p[:2] for p in pts),'collector','ramp',pts,
                           f'interchange:{direction}:{idx}',role):continue
                probe=RoadMap('ramp_probe',t,tuple(nodes.values()),tuple(sections))
                if any(key in (v['first'],v['second']) for v in crossing_audit(probe)['illegal']):
                    sections.pop();continue
                break


def _ramp_curve(a,b,sign,role):
    handle=min(abs(b[0]-a[0])*.55,220.)
    c1=(a[0]+.30*(b[0]-a[0]),a[1]+.30*(b[1]-a[1]))
    c2=(b[0]-.30*(b[0]-a[0]),b[1]-.30*(b[1]-a[1]))
    if role=='on_ramp':c2=(b[0]-sign*handle,b[1])
    else:c1=(a[0]+sign*handle,a[1])
    xy=[]
    for k in range(25):
        u=k/24
        xy.append(tuple((1-u)**3*a[i]+3*(1-u)**2*u*c1[i]+3*(1-u)*u*u*c2[i]+u**3*b[i] for i in (0,1)))
    lengths=[0.]
    for x,y in zip(xy,xy[1:]):lengths.append(lengths[-1]+math.dist(x,y))
    pts=tuple((*p,a[2]+(b[2]-a[2])*d/lengths[-1]) for p,d in zip(xy,lengths))
    return (a,*pts[1:-1],b)
