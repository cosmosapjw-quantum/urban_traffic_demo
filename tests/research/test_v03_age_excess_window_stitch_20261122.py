"""Finite-horizon source age-excess conservation composes at checkpoint time."""
from fractions import Fraction as F
from metroflow.v1.age_excess_transport import (
    AgeBoundary,AgeCohort,finite_age_excess_transport,
)


def test_checkpoint_stitching_cancels_all_age_excess_internal_boundary():
    initial=(AgeCohort(1,2,0),)
    out3=AgeBoundary(F(3),1,"out",1,0)
    out5=AgeBoundary(F(5),1,"out",1,0)
    us=(F(0),F(1),F(2),F(3),F(4),F(5))
    full=finite_age_excess_transport(F(0),F(5),initial,
                                     (out3,out5),us)
    for boundary in (F(3),F(4)):
        first=finite_age_excess_transport(
            F(0),boundary,initial,(out3,),us)
        second=finite_age_excess_transport(
            boundary,F(5),(AgeCohort(1,1,0),),(out5,),us)
        for u in us:
            a,b,c=first[(1,u)],second[(1,u)],full[(1,u)]
            assert a.terminal_loss==b.initial_loss
            assert a.output_loss+b.output_loss==c.output_loss
            assert a.tail_stock_time+b.tail_stock_time==c.tail_stock_time
            assert a.entry_loss+b.entry_loss==c.entry_loss
            assert a.output_delay_square+b.output_delay_square==c.output_delay_square
            # The artificial intermediate checkpoint boundary cancels.
            assert (a.initial_loss-a.terminal_loss+
                    b.initial_loss-b.terminal_loss)==(
                        c.initial_loss-c.terminal_loss)


def test_at_checkpoint_event_is_assigned_once_to_preceding_closed_window():
    # t1=2 is a boundary: output at exactly t1 belongs to (t0,t1],
    # never again to (t1,T], as required for deterministic replay identity.
    m=F(3,2)
    out=AgeBoundary(F(2),1,"out",m,0)
    initial=(AgeCohort(1,2*m,0),)
    a=finite_age_excess_transport(F(0),F(2),initial,(out,),(F(1),))
    b=finite_age_excess_transport(F(2),F(4),
        (AgeCohort(1,m,0),),(),(F(1),))
    full=finite_age_excess_transport(F(0),F(4),initial,(out,),(F(1),))
    assert a[(1,F(1))].output_mass==m
    assert b[(1,F(1))].output_mass==0
    assert full[(1,F(1))].output_mass==m
    assert (a[(1,F(1))].tail_stock_time+
            b[(1,F(1))].tail_stock_time)==full[(1,F(1))].tail_stock_time
    assert a[(1,F(1))].terminal_loss==b[(1,F(1))].initial_loss
