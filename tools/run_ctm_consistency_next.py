"""Service-clock falsification and independent continuum convergence campaign.

The scientific calculations use the standard library. PNG export is optional.
"""
from dataclasses import replace
from pathlib import Path
import json
import math
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metroflow.pure_traffic.ctm import CTMConfig, LinkSpec, MovementSpec, NetworkSpec, VehicleRequest, initialize_state, simulate
from metroflow.pure_traffic.fluid_reference import FundamentalDiagram, solve_riemann
from metroflow.pure_traffic.scenarios import build_diamond_bottleneck_scenario
from validate_pure_python_ctm_research import _run_case, CASES


def fixture(dt, mode, green=(), two_links=False):
    links=[LinkSpec('a','o','m',1000.,1,15.,5.,150.,1800.)]
    moves=[MovementSpec('a',None,1800.,green_cycle=green)]
    route=('a',)
    if two_links:
        links.append(LinkSpec('b','m','d',1000.,1,15.,5.,150.,1800.))
        moves=[MovementSpec('a','b',1800.,green_cycle=green),MovementSpec('b',None,1800.)]
        route=('a','b')
    net=NetworkSpec(tuple(links),tuple(moves))
    req=tuple(VehicleRequest(i,0,route) for i in range(100))
    cfg=CTMConfig(tick_seconds=dt,node_token_mode=mode,forced_cell_count_by_link={l.link_id:1 for l in links})
    state=initialize_state(net,req,cfg)
    state=replace(state,cells=((tuple(range(100)),),)+(((),),)*(len(links)-1),
                  admitted_ticks=(0,)*100,released_count=100,
                  cumulative_source_admissions=(100,)+(0,)*(len(links)-1))
    if two_links:
        state=replace(state,entry_residuals=(0.,.5))
    return net,req,cfg,state


def run_service(dt,mode,green=(),two_links=False):
    net,req,cfg,state=fixture(dt,mode,green,two_links)
    result=simulate(net,req,cfg,ticks=round(100/dt),initial_state=state)
    key=('a','b') if two_links else ('a',None)
    return {'dt_s':dt,'mode':mode,'flow_vehicles':result.cumulative_movement_flow[key],
            'mass_error':result.final_state.mass_balance_error,
            'fingerprint':result.fingerprint,
            'trace':[(s.tick*dt,s.cumulative_movement_flow[key]) for s in result.snapshots]}


def main(out):
    out.mkdir(parents=True,exist_ok=True)
    service=[run_service(dt,mode) for dt in (.5,1.,2.,5.,10.) for mode in ('legacy','coupled_credit')]
    signal=[run_service(1.,mode,(True,False)) for mode in ('legacy','coupled_credit')]
    phases=[run_service(1.,mode,two_links=True) for mode in ('legacy','coupled_credit')]
    fd=FundamentalDiagram(15.,5.,.15)
    refinement={}
    for name,states in [('shock',(.02,.10)),('expansion',(.12,.01))]:
        rows=[]
        for n in (100,200,400,800):
            result=solve_riemann(fd,*states,100.,n_cells=n)
            temporal=[solve_riemann(fd,*states,t,n_cells=n) for t in range(10,101,10)]
            result['time_sample_mean_profile_l1']=math.fsum(r['l1_profile_error_vehicles'] for r in temporal)/len(temporal)
            result['time_sample_mean_cell_average_l1']=math.fsum(r['l1_error_vehicles'] for r in temporal)/len(temporal)
            rows.append(result)
        refinement[name]=rows
    matrix=[_run_case(*case) for case in CASES]
    sc=build_diamond_bottleneck_scenario(seed=20261023,vehicles=320,release_batch=4)
    diamond=simulate(sc.network,sc.requests,sc.config,ticks=220,incidents=sc.incidents)
    diamond_summary={'fingerprint':diamond.fingerprint,'completed':diamond.final_state.completed_count,
        'clear_tick':next((s.tick for s in diamond.snapshots if s.completed_count==320),None),
        'mass_error':diamond.final_state.mass_balance_error,'holding_events':diamond.node_holding_events,
        'mean_travel_time_s':math.fsum(diamond.completed_travel_times_s)/len(diamond.completed_travel_times_s),
        'max_cell_occupancy':max(r for s in diamond.snapshots for rs in s.link_cell_occupancy_ratio.values() for r in rs)}
    checks={
        'all_saturated_rates':all(r['flow_vehicles']==50 for r in service if r['mode']=='coupled_credit'),
        'green_pulses':signal[-1]['flow_vehicles']==25,
        'opposed_clock_phases':phases[-1]['flow_vehicles']==50,
        'matrix':all(r['status']=='PASS' for r in matrix),
        'profile_error_convergence':all(all(a['l1_profile_error_vehicles']>b['l1_profile_error_vehicles'] for a,b in zip(rows,rows[1:])) for rows in refinement.values()),
        'temporal_mean_error_convergence':all(all(a['time_sample_mean_profile_l1']>b['time_sample_mean_profile_l1'] for a,b in zip(rows,rows[1:])) for rows in refinement.values()),
        'fluid_boundary_mass':all(abs(r['mass_balance_error_vehicles'])<1e-9 for rows in refinement.values() for r in rows),
        'diamond_clears':diamond_summary['completed']==320,
    }
    result={'schema':'traffic_consistency_next_v2','service':service,'alternating_signal':signal,
        'opposed_phases':phases,'refinement':refinement,'matrix':matrix,'diamond':diamond_summary,
        'checks':checks,'all_checks_pass':all(checks.values()),
        'scope':'Rate-consistent packetized node service and separate continuous corridor oracle; no proof of integer-network continuum convergence.'}
    (out/'TRAFFIC_RESULTS.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        plt=None
    if plt is not None:
        for filename,rows,title in [('saturated_service',service,'Saturated discharge: 0.5 veh/s'),('signal_service',signal,'Alternating green: fractional capacity'),('phase_service',phases,'Anti-phase sending and receiving clocks')]:
            fig,ax=plt.subplots(figsize=(8,4.5))
            for row in rows:
                if filename=='saturated_service' and row['dt_s'] not in (.5,1.):
                    continue
                ax.step(*zip(*row['trace']),where='post',label=f"{row['mode']}, dt={row['dt_s']:g}s")
            rate=.25 if filename=='signal_service' else .5
            ax.plot([0,100],[0,100*rate],linestyle='--',label='continuous service target')
            ax.set(xlabel='Time [s]',ylabel='Cumulative vehicles',title=title); ax.legend(); fig.tight_layout()
            fig.savefig(out/f'{filename}.png',dpi=160); plt.close(fig)
        for name,rows in refinement.items():
            fig,ax=plt.subplots(figsize=(8,4.5))
            for row in rows[::2]:
                ax.plot(row['cell_centres_m'],row['density_veh_m'],label=f"Godunov N={row['n_cells']}")
            row=rows[-1]
            ax.plot(row['cell_centres_m'],row['exact_density_veh_m'],linestyle='--',label='exact cell average, N=800')
            ax.set(xlabel='Position [m]',ylabel='Density [veh/m]',title=f'{name.title()} at t=100 s'); ax.legend(); fig.tight_layout()
            fig.savefig(out/f'{name}_profile.png',dpi=160); plt.close(fig)
        fig,ax=plt.subplots(figsize=(8,4.5))
        for name,rows in refinement.items():
            ax.loglog([r['dx_m'] for r in rows],[r['l1_profile_error_vehicles'] for r in rows],marker='o',label=name+' full-profile error')
        ax.set(xlabel='Cell length [m]',ylabel='Integrated absolute density error [veh]',title='Continuum oracle refinement (not integer-network convergence)')
        ax.legend(); fig.tight_layout(); fig.savefig(out/'refinement.png',dpi=160); plt.close(fig)
    print(json.dumps({'checks':checks,'diamond':diamond_summary},indent=2))
    return 0 if all(checks.values()) else 2

if __name__=='__main__':
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv)>1 else Path('artifacts/next_loop_20261023/traffic')))
