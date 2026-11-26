// Access-resolved multiclass FIFO projection with shared standing length (m)
// and aggregate receiving tokens per native 10 s clock. Separate research
// closure: fixed paths, whole batches, no bus passenger or land-use feedback.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <deque>
#include <functional>
#include <iomanip>
#include <iostream>
#include <queue>
#include <stdexcept>
#include <tuple>
#include <vector>

struct Group {
    int forward, backward, purpose;
    double mass, origin_access, destination_access;
    int cls, phase_group;
};
enum Phase { Release, Enter, Exit, Complete, Service, Wake };
struct Event {
    double t, mass, q, began;
    std::uint64_t key;
    int group, edge;
    Phase phase;
    bool returning;
};
// A link owns all on-road cohorts, including an exit-blocked head.
// A downstream request refers to that head; it does not own another copy.
struct Request { int source; Event source_batch; double requested; };
struct Link {
    double travel=0, entry=0, capacity=0, storage=0, free_at=0, finish=0;
    long long receive_epoch=-1; long double remaining=0, received=0, peak_receive_ratio=0;
    long double stock=0, peak=0, wait_veh_s=0, blocked_veh_s=0;
    std::deque<Event> fifo;
    std::deque<Request> requests;
    bool scheduled=false, wake=false;
};
// Each cohort retains one equal-mass atom per rank stratum. The mirrored
// strata share complementary phases, so total mass and first rank moment
// are unchanged in real arithmetic. Seed 0 is the historical midpoint arm.
static std::uint64_t mix64(std::uint64_t x) {
    x+=0x9e3779b97f4a7c15ULL;
    x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;
    x=(x^(x>>27))*0x94d049bb133111ebULL;
    return x^(x>>31);
}
static double rank_phase(int group,int j,int n,std::uint64_t seed) {
    if(seed==0 || j==n-1-j) return (j+0.5)/n;
    int k=std::min(j,n-1-j);
    auto z=mix64(seed^mix64(static_cast<std::uint64_t>(group))^mix64(static_cast<std::uint64_t>(k)+0x58e4e3ULL));
    double u=(static_cast<double>(z>>12)+0.5)*0x1p-52;
    double q=(k+u)/n;
    return j==k?q:1.-q;
}
static double tick(double t) { return 10.*std::ceil(t/10.-1e-12); }
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
    if (argc!=8) throw std::runtime_error("input bin shocked_link factor passages horizon phase_seed");
    const double horizon_limit=std::stod(argv[6]);
    const std::uint64_t phase_seed=std::stoull(argv[7]);
    constexpr std::array<double,3> footprint{5.,10.,12.};
    std::ifstream f(argv[1]);
    int link_count, path_count, group_count, profiles;
    double dwell;
    if (!(f>>link_count>>path_count>>group_count>>profiles>>dwell)) throw std::runtime_error("bad input header");
    double bin=std::stod(argv[2]), shock=std::stod(argv[4]); int shock_id=std::stoi(argv[3]);
    if (!(bin>0 && shock>0) || shock_id>=link_count) throw std::runtime_error("invalid scenario");
    std::vector<Link> links(link_count);
    for (auto &link:links) {
        f>>link.travel>>link.entry>>link.capacity>>link.storage;
        if (!(link.travel>0 && link.entry>0 && link.capacity>0 && link.storage>0)
            || !std::isfinite(link.travel+link.entry+link.capacity+link.storage)) throw std::runtime_error("invalid road");
    }
    if(shock_id>=0) links[shock_id].capacity*=shock;
    std::vector<std::vector<int>> paths(path_count);
    for (auto& path:paths) {
        int n; f>>n; if(n<=0) throw std::runtime_error("empty route");
        path.resize(n); for(int& e:path) {
            f>>e; if(e<0 || e>=link_count) throw std::runtime_error("invalid road id");
        }
    }
    for(const auto& p:paths) for(size_t i=1;i<p.size();++i)
        if(p[i]==p[i-1]) throw std::runtime_error("adjacent repeated road");
    std::ifstream kinetics(argv[5]); int route_n;
    if(!(kinetics>>route_n) || route_n!=path_count) throw std::runtime_error("kinetic layout");
    std::vector<std::vector<double>> passage(path_count);
    for(int r=0;r<path_count;++r) {
        int n; if(!(kinetics>>n) || n!=int(paths[r].size())) throw std::runtime_error("kinetic path length");
        passage[r].resize(n);
        for(auto& dt:passage[r]) if(!(kinetics>>dt) || !(dt>0) || !std::isfinite(dt)) throw std::runtime_error("invalid passage");
    }
    std::vector<std::array<double,4>> windows(profiles);
    for(auto& w:windows) for(double& time:w) f>>time;
    std::vector<Group> groups(group_count);
    for(auto& g:groups) {
        f>>g.forward>>g.backward>>g.purpose>>g.mass>>g.origin_access>>g.destination_access>>g.cls>>g.phase_group;
        if(!f || !(g.mass>0) || g.origin_access<0 || g.destination_access<0
             || g.purpose<0 || g.purpose>=profiles || g.forward<0 || g.backward< -1
             || std::max(g.forward,g.backward)>=path_count || g.cls<0 || g.cls>=3 || g.phase_group<0
             || !std::isfinite(g.mass+g.origin_access+g.destination_access)) throw std::runtime_error("invalid cohort");
    }
    std::priority_queue<Event,std::vector<Event>,Later> queue;
    std::cout<<std::setprecision(17);
    std::vector<int> cohort_bins(group_count);
    std::vector<std::uint64_t> cohort_offset(group_count);
    std::uint64_t next_key=0;
    long double daily_out=0;
    std::array<long double,3> expected{};
    std::array<Ledger,3> byclass{};
    auto first_departure=[&](int i,int j) {
        const auto& g=groups[i]; const auto& w=windows[g.purpose];
        const auto bins=cohort_bins[i];
        const double q=rank_phase(g.phase_group,j,bins,phase_seed);
        // Every group gets an independent stable key range, also with lazy departures.
        queue.push({w[0]+q*(w[1]-w[0]),g.mass/bins,q,0,cohort_offset[i]+j,i,0,Release,false});
    };
    for(int i=0;i<group_count;++i) {
        const auto& g=groups[i]; const auto& w=windows[g.purpose];
        const int bins=std::max(1,int(std::ceil(std::max(w[1]-w[0],w[3]-w[2])/bin)));
        if(w[1]<w[0] || (g.backward>=0 && !(w[3]>w[2]))) throw std::runtime_error("invalid departure window");
        for(int r:{g.forward,g.backward}) if(r>=0) for(int j:paths[r])
            if(g.mass/bins*footprint[g.cls] > links[j].storage ||
               g.mass/bins > 10.*links[j].entry) throw std::runtime_error("batch exceeds link storage or tick supply; refine bin");
        daily_out+=g.mass;
        expected[g.cls]+=g.mass*(g.backward>=0?2:1);
        cohort_bins[i]=bins; cohort_offset[i]=next_key; next_key+=bins;
        if(phase_seed) {
            // Validate a complementary pair and both strata at each cohort
            // (the exhaustive independent fixture covers every rank).
            for(int j:{0,bins/2,bins-1}) {
                double q=rank_phase(g.phase_group,j,bins,phase_seed);
                if(!(q>=double(j)/bins && q<=double(j+1)/bins) ||
                   std::abs(q+rank_phase(g.phase_group,bins-1-j,bins,phase_seed)-1.)>4e-16)
                    throw std::runtime_error("departure rank outside mirrored stratum");
            }
        }
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
    auto route=[&](const Event& b){const auto& g=groups[b.group]; return b.returning?g.backward:g.forward;};
    auto cls=[&](const Event& b){return groups[b.group].cls;};
    auto length=[&](const Event& b){return b.mass*footprint[cls(b)];};
    auto signal=[&](int i,double t,Phase phase){queue.push({t,0,0,0,next_key++,i,0,phase,false});};
    auto wake=[&](int i,double t){
        auto& l=links[i];
        if(!l.requests.empty() && !l.wake) {l.wake=true;signal(i,t,Wake);}
    };
    auto schedule=[&](int i,double t){
        auto& l=links[i]; if(l.scheduled||l.fifo.empty()) return;
        const auto& b=l.fifo.front();
        double ready=b.t+passage[route(b)][b.edge];
        double begin=std::max(ready,l.free_at);
        l.wait_veh_s+=b.mass*(begin-ready);
        l.finish=begin+b.mass/l.capacity;
        l.scheduled=true; signal(i,std::max(t,tick(l.finish)),Service);
    };
    auto admit=[&](int i,Event b,double t){
        auto& l=links[i];
        b.t=t; l.fifo.push_back(b); l.stock+=length(b);
        l.remaining=std::max(0.L,l.remaining-b.mass);
        l.received+=b.mass;
        l.peak_receive_ratio=std::max(l.peak_receive_ratio,l.received/(10.*l.entry));
        if(l.received>10.*l.entry+1e-9L) throw std::runtime_error("aggregate receiving overflow");
        l.peak=std::max(l.peak,l.stock);
        if(l.stock>l.storage+1e-9L || l.remaining<0) throw std::runtime_error("storage overflow");
        if(!b.edge) {book[b.returning].admitted+=b.mass;byclass[cls(b)].admitted+=b.mass;}
        schedule(i,t);
    };
    auto depart=[&](int i,double t,bool was_blocked){
        auto& l=links[i]; if(!l.scheduled||l.fifo.empty()) throw std::runtime_error("invalid head departure");
        Event b=l.fifo.front();l.fifo.pop_front();l.stock-=length(b);
        if(l.fifo.empty()) {if(std::fabs(l.stock)>1e-7L) throw std::runtime_error("empty stock mismatch");l.stock=0;}
        if(l.stock < -1e-9L) throw std::runtime_error("negative stock");
        l.free_at=was_blocked?std::max(l.finish,t):l.finish;
        l.scheduled=false;
        wake(i,t);schedule(i,t); return b;
    };
    std::uint64_t blocked=0, transfers=0,storage_blocks=0,rate_blocks=0;
    auto request=[&](int i,Request r,double t){
        auto& l=links[i];
        const Event& b=r.source<0?r.source_batch:links[r.source].fifo.front();
        if(!l.requests.empty() || l.stock+length(b)>l.storage+1e-10L) ++blocked;
        l.requests.push_back(r);wake(i,t);
    };
    if (!(horizon_limit>0 && horizon_limit<=86400.)) throw std::runtime_error("invalid horizon");
    std::vector<double> horizons;
    for(double t:{25720.,28800.,43200.,64800.,86400.}) if(t<horizon_limit) horizons.push_back(t);
    horizons.push_back(horizon_limit);
    for(double horizon:horizons) {
        while(!queue.empty() && queue.top().t<=horizon) {
            Event e=queue.top();queue.pop();++event_count;
            if(e.phase==Wake) {
                int i=e.group;auto& l=links[i];l.wake=false;
                const auto epoch=std::llround(e.t/10.);
                if(std::fabs(e.t-10.*epoch)>1e-8 || epoch<l.receive_epoch) throw std::runtime_error("receiving clock");
                if(epoch!=l.receive_epoch) {l.receive_epoch=epoch;l.remaining=10.*l.entry;l.received=0;}
                while(!l.requests.empty()) {
                    Request r=l.requests.front();
                    Event b=r.source<0?r.source_batch:links[r.source].fifo.front();
                    if(l.stock+length(b)>l.storage+1e-10L) {++storage_blocks;break;}
                    if(b.mass>l.remaining+1e-12L) {++rate_blocks;wake(i,10.*(epoch+1));break;}
                    l.requests.pop_front();
                    l.blocked_veh_s+=b.mass*(e.t-r.requested);
                    if(r.source>=0) {b=depart(r.source,e.t,e.t>r.requested);++b.edge;++transfers;}
                    admit(i,b,e.t);
                }
                continue;
            }
            if(e.phase==Service) {
                int i=e.group;const auto& l=links[i];
                if(l.fifo.empty()||!l.scheduled) throw std::runtime_error("stale service");
                Event b=l.fifo.front();const auto& p=paths[route(b)];
                if(b.edge+1==int(p.size())) {
                    b=depart(i,e.t,false);book[b.returning].exited+=b.mass;byclass[cls(b)].exited+=b.mass;
                    const auto& g=groups[b.group];
                    push(b,e.t+(b.returning?g.origin_access:g.destination_access),Complete);
                } else request(p[b.edge+1],{i,{},e.t},e.t);
                continue;
            }
            auto& g=groups[e.group];auto& l=book[e.returning];const auto& p=paths[route(e)];
            switch(e.phase) {
            case Release:
                if(!e.returning) {
                    int j=static_cast<int>(e.key-cohort_offset[e.group]);
                    if(j+1<cohort_bins[e.group]) first_departure(e.group,j+1);
                }
                l.released+=e.mass;byclass[cls(e)].released+=e.mass;e.began=e.t;e.edge=0;
                push(e,10.+tick(e.t+(e.returning?g.destination_access:g.origin_access)),Enter);break;
            case Enter:request(p[0],{-1,e,e.t},e.t);break;
            case Complete:
                l.completed+=e.mass;l.vehicle_trip_seconds+=e.mass*(e.t-e.began);
                byclass[cls(e)].completed+=e.mass;byclass[cls(e)].vehicle_trip_seconds+=e.mass*(e.t-e.began);
                completions[g.purpose][e.returning]+=e.mass;
                if(!e.returning && g.backward>=0) {
                    e.returning=true;const auto& w=windows[g.purpose];
                    push(e,std::max(w[2]+e.q*(w[3]-w[2]),e.t+dwell),Release);
                }
                break;
            default:throw std::runtime_error("invalid phase");
            }
        }
        long double road=0,active=0,origin_wait=0,blocked_wait=0,stockerr=0,peakratio=0,peak_receive=0;
        std::array<long double,3> class_road{},class_active{};
        for(const auto& l:links) {
            long double occupied=0;
            for(const auto& b:l.fifo) {occupied+=length(b);road+=b.mass;class_road[cls(b)]+=b.mass;class_active[cls(b)]+=b.mass;}
            stockerr=std::max(stockerr,std::fabs(occupied-l.stock));
            peakratio=std::max(peakratio,l.peak/l.storage);
            peak_receive=std::max(peak_receive,l.peak_receive_ratio);
            for(const auto& r:l.requests) {
                double m=r.source<0?r.source_batch.mass:links[r.source].fifo.front().mass;
                if(r.source<0) {origin_wait+=m;class_active[cls(r.source_batch)]+=m;}
                blocked_wait+=m*(horizon-r.requested);
            }
        }
        active=road+origin_wait;
        auto pending=queue;
        while(!pending.empty()) {const auto& e=pending.top();if(e.phase==Enter||e.phase==Complete){active+=e.mass;class_active[cls(e)]+=e.mass;}pending.pop();}
        long double released=book[0].released+book[1].released, completed=book[0].completed+book[1].completed;
        long double admitted=book[0].admitted+book[1].admitted, exited=book[0].exited+book[1].exited;
        long double err=std::max({std::fabs(released-completed-active),std::fabs(admitted-exited-road)});
        if(err>1e-8L*std::max(1.L,released)||book[1].released>book[0].completed+1e-8L||peakratio>1+1e-9L||stockerr>1e-6L||peak_receive>1+1e-9L)
            throw std::runtime_error("carrier/return/storage ledger violated");
        for(int c=0;c<3;++c) {
            const auto& z=byclass[c];
            const auto error=std::max(std::fabs(z.released-z.completed-class_active[c]),std::fabs(z.admitted-z.exited-class_road[c]));
            if(error>1e-8L*std::max(1.L,z.released) || z.released>expected[c]+1e-8L)
                throw std::runtime_error("class vehicle ledger violated");
            std::cout<<"class "<<horizon<<" "<<c<<" "<<expected[c]<<" "<<z.released<<" "<<z.admitted<<" "<<z.exited<<" "<<z.completed<<" "<<class_active[c]<<" "<<class_road[c]<<" "<<error<<" "<<z.vehicle_trip_seconds<<std::endl;
        }
        std::cout<<"snap "<<horizon<<" "<<released<<" "<<admitted<<" "<<exited<<" "<<completed<<" "<<active<<" "<<road<<" "<<err<<" "<<origin_wait<<" "<<peakratio<<" "<<blocked<<" "<<blocked_wait<<" "<<storage_blocks<<" "<<rate_blocks<<" "<<stockerr<<" "<<peak_receive<<std::endl;
    }
    long double wait=0,spill=0;int worst=0;
    for(int i=0;i<link_count;++i){auto& l=links[i];wait+=l.wait_veh_s;spill+=l.blocked_veh_s;if(l.blocked_veh_s>links[worst].blocked_veh_s)worst=i;}
    std::cout<<"end "<<daily_out<<" "<<initial_batches<<" "<<event_count<<" "<<wait<<" "<<spill<<" "<<worst<<" "<<links[worst].blocked_veh_s<<" "<<transfers<<" "<<book[0].vehicle_trip_seconds+book[1].vehicle_trip_seconds<<std::endl;
    for(int k=0;k<profiles;++k) std::cout<<"purpose "<<k<<" "<<completions[k][0]<<" "<<completions[k][1]<<"\n";
    return 0;
}
