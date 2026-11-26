#define main spillback_driver_main
#include "spillback_queue.cpp"
#undef main
#include <cassert>
#include <set>
int main() {
    std::uint64_t count=0;
    std::set<double> distinct;
    for(int g=0;g<100;++g) {
        distinct.insert(rank_phase(g,0,8,7));
        for(int n=1;n<=256;++n) {
            long double sum=0;
            double prev=-1;
            for(int j=0;j<n;++j) {
                const double q=rank_phase(g,j,n,7);
                assert(q>prev && q>=double(j)/n && q<=double(j+1)/n);
                assert(std::abs(q+rank_phase(g,n-1-j,n,7)-1.)<5e-16);
                assert(rank_phase(g,j,n,0)==(j+.5)/n);
                sum+=q;prev=q;++count;
            }
            assert(std::abs(sum-n/2.L)<1e-12L);
        }
    }
    assert(distinct.size()==100);
    std::cout<<"rank checks "<<count<<" distinct phases "<<distinct.size()<<"\n";
}
