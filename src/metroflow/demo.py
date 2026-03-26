from metroflow.core.state import make_empty_world_state
from metroflow.core.contracts import default_simulation_config
from metroflow.sim.scheduler import scheduler_decision

def main() -> None:
    world = make_empty_world_state()
    config = default_simulation_config()
    decision = scheduler_decision(step_idx=0, schedule=config.schedule)
    print("MetroFlow starter skeleton")
    print("graph_version:", world.graph.version)
    print("scheduler decision:", decision)

if __name__ == "__main__":
    main()
