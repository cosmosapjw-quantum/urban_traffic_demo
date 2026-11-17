ClearAll[m,b,h,d1,d2,w1,w2,z1,z2];
queued=m(w1(1-z1)+w2(1-z2)); retired=m(w1 z1+w2 z2);
{FullSimplify[queued+retired-m,Assumptions->w1+w2==1],
 FullSimplify[b queued+b retired-m b,Assumptions->w1+w2==1],
 FullSimplify[(b+d1+h<=t)==(d1<=t-b-h),Assumptions->Element[{b,d1,h,t},Reals]]}
