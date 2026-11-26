// Ordered deterministic point queues on a directed fixed-route network.
// Input types are SI seconds, veh/s and vehicle mass. No resident particle is required.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <queue>
#include <stdexcept>
#include <tuple>
#include <vector>

struct Link {
    double travel, capacity;
    double free_at=0, delay_veh_s=0, traversed_mass=0, max_wait_s=0;
};
struct Group {
    int forward, backward, purpose;
    double mass, origin_access, destination_access;
};
enum Phase { Release, Enter, Exit, Complete };
struct Event {
    double t, mass, q, began;
    std::uint64_t key;
    int group, edge;
    Phase phase;
    bool returning;
};
struct Later {
    bool operator()(const Event& a,const Event& b) const {
        return std::tie(a.t,a.key)>std::tie(b.t,b.key);
    }
};
// Accumulate vehicle mass and first moments with wider intermediates.
struct Ledger {
    long double released=0, admitted=0, exited=0, completed=0, vehicle_trip_seconds=0;
};
int main(int argc,char** argv) {
    if (argc!=5 && argc!=6) throw std::runtime_error("input bin_width_s shocked_link factor [prefix_s]");
    const double horizon_limit=argc==6 ? std::stod(argv[5]) : 86400.;
    std::ifstream f(argv[1]);
    int link_count, path_count, group_count, profiles;
    double dwell;
    if (!(f>>link_count>>path_count>>group_count>>profiles>>dwell)) throw std::runtime_error("bad input header");
    double bin=std::stod(argv[2]), shock=std::stod(argv[4]); int shock_id=std::stoi(argv[3]);
    if (!(bin>0 && shock>0) || shock_id>=link_count) throw std::runtime_error("invalid scenario");
    std::vector<Link> links(link_count);
    for (auto &link:links) {
        f>>link.travel>>link.capacity;
        if (!(link.travel>0 && link.capacity>0)) throw std::runtime_error("invalid road");
    }
    if(shock_id>=0) links[shock_id].capacity*=shock;
    std::vector<std::vector<int>> paths(path_count);
    for (auto& path:paths) {
        int n; f>>n; if(n<=0) throw std::runtime_error("empty route");
        path.resize(n); for(int& e:path) {
            f>>e; if(e<0 || e>=link_count) throw std::runtime_error("invalid road id");
        }
    }
    std::vector<std::array<double,4>> windows(profiles);
    for(auto& w:windows) for(double& time:w) f>>time;
    std::vector<Group> groups(group_count);
    for(auto& g:groups) {
        f>>g.forward>>g.backward>>g.purpose>>g.mass>>g.origin_access>>g.destination_access;
        if(!f || !(g.mass>0) || g.origin_access<0 || g.destination_access<0
             || g.purpose<0 || g.purpose>=profiles || std::min(g.forward,g.backward)<0
             || std::max(g.forward,g.backward)>=path_count) throw std::runtime_error("invalid cohort");
    }
    std::priority_queue<Event,std::vector<Event>,Later> queue;
    std::cout<<std::setprecision(17);
    std::vector<int> cohort_bins(group_count);
    std::vector<std::uint64_t> cohort_offset(group_count);
    std::uint64_t next_key=0;
    long double daily_out=0;
    auto first_departure=[&](int i,int j) {
        const auto& g=groups[i]; const auto& w=windows[g.purpose];
        const auto bins=cohort_bins[i];
        const double q=(j+0.5)/bins;
        // Every group gets an independent stable key range, also with lazy departures.
        queue.push({w[0]+q*(w[1]-w[0]),g.mass/bins,q,0,cohort_offset[i]+j,i,0,Release,false});
    };
    for(int i=0;i<group_count;++i) {
        const auto& g=groups[i]; const auto& w=windows[g.purpose];
        const int bins=std::ceil(std::max(w[1]-w[0],w[3]-w[2])/bin);
        if(bins<1) throw std::runtime_error("empty departure window");
        daily_out+=g.mass;
        cohort_bins[i]=bins; cohort_offset[i]=next_key; next_key+=bins;
        first_departure(i,0);
    }
    const auto initial_batches=next_key;
    std::array<Ledger,2> book{};
    std::vector<std::array<long double,2>> completions(profiles);
    std::uint64_t event_count=0;
    auto push=[&](Event ev,double t,Phase phase){
        if(t<ev.t || !std::isfinite(t)) throw std::runtime_error("noncausal event");
        ev.t=t; ev.phase=phase; ev.key=next_key++; queue.push(ev);
    };
    if (!(horizon_limit>0 && horizon_limit<=86400.)) throw std::runtime_error("invalid horizon");
    std::vector<double> horizons;
    for (double t:{25720.,28800.,43200.,64800.,86400.}) if(t<horizon_limit) horizons.push_back(t);
    horizons.push_back(horizon_limit);
    for(double horizon:horizons) {
        while(!queue.empty() && queue.top().t<=horizon) {
            Event e=queue.top();queue.pop();++event_count;
            auto& g=groups[e.group]; auto& l=book[e.returning];
            auto& path=paths[e.returning?g.backward:g.forward];
            switch(e.phase) {
            case Release:
                if (!e.returning) {
                    int j=static_cast<int>(e.key-cohort_offset[e.group]);
                    if (j+1<cohort_bins[e.group]) first_departure(e.group,j+1);
                }
                l.released+=e.mass; e.began=e.t; e.edge=0;
                push(e,e.t+(e.returning ? g.destination_access:g.origin_access),Enter);break;
            case Enter: {
                if(!e.edge) l.admitted+=e.mass;
                auto& link=links[path.at(e.edge)];
                double ready=e.t+link.travel;
                double wait=std::max(0.,link.free_at-ready);
                double finish=ready+wait+e.mass/link.capacity;
                link.free_at=finish; link.delay_veh_s+=e.mass*wait;
                link.traversed_mass+=e.mass; link.max_wait_s=std::max(link.max_wait_s,wait);
                ++e.edge;
                push(e, finish, e.edge==static_cast<int>(path.size()) ? Exit : Enter);
                break;
            }
            case Exit:
                l.exited+=e.mass;
                push(e,e.t+(e.returning ? g.origin_access:g.destination_access),Complete);break;
            case Complete:
                l.completed+=e.mass; l.vehicle_trip_seconds+=e.mass*(e.t-e.began);
                completions[g.purpose][e.returning]+=e.mass;
                if(!e.returning) {
                    e.returning=true; const auto& w=windows[g.purpose];
                    double ret=w[2]+e.q*(w[3]-w[2]);
                    push(e,std::max(ret,e.t+dwell),Release);
                }
                break;
            }
        }
        // Sum an independent inventory of future events, not a residual called stock.
        auto pending=queue;
        long double active=0, road=0;
        while(!pending.empty()) {
            const auto& e=pending.top();
            if(e.phase!=Release) active+=e.mass;
            if(e.phase==Exit || (e.phase==Enter && e.edge>0)) road+=e.mass;
            pending.pop();
        }
        long double released=book[0].released+book[1].released;
        long double completed=book[0].completed+book[1].completed;
        long double admitted=book[0].admitted+book[1].admitted;
        long double exited=book[0].exited+book[1].exited;
        long double err=std::max(std::fabs(released-completed-active),std::fabs(admitted-exited-road));
        if(err>1e-8L*std::max(1.L,released) || book[1].released>book[0].completed+1e-8L)
            throw std::runtime_error("carrier/return ledger violated");
        std::cout<<"snap "<<horizon<<" "<<released<<" "<<admitted<<" "<<exited<<" "<<completed<<" "<<active<<" "<<road<<" "<<err<<"\n";
    }
    auto worst=std::max_element(links.begin(),links.end(),[](const Link& a,const Link& b){
        return a.delay_veh_s<b.delay_veh_s;
    });
    long double total_wait=0;for(const auto& link:links) total_wait+=link.delay_veh_s;
    std::cout<<"end "<<daily_out<<" "<<initial_batches<<" "<<event_count<<" "<<total_wait<<" "
             <<(worst-links.begin())<<" "<<worst->delay_veh_s<<" "<<worst->max_wait_s<<" "
             <<book[0].vehicle_trip_seconds+book[1].vehicle_trip_seconds<<"\n";
    for(int k=0;k<profiles;++k)
        std::cout<<"purpose "<<k<<" "<<completions[k][0]<<" "<<completions[k][1]<<"\n";
}
