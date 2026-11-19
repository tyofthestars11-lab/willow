"""Tests for mac/adapt.py (pure Python). Run from the repository root: python3 -m unittest discover -s mac/tests -q"""
import os, random, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapt import FRAME_S, InputGain, Playout, PRIOR_HOLD_S


def playout(rtts=(), replies=(), capacity=0.4, max_hold=4.0):
    p = Playout(capacity, max_hold)
    for r in rtts: p.observe_rtt(r)
    for audio, gen, *stall in replies:
        if stall: p.observe_stall(stall[0])
        p.observe_reply(audio, gen)
    return p


class Lead(unittest.TestCase):
    def test_before_any_measurement_it_is_half_the_capacity(self):
        self.assertAlmostEqual(playout().lead(), 0.2)

    def test_a_steady_link_needs_only_a_few_frames(self):
        self.assertAlmostEqual(playout(rtts=[0.005] * 20).lead(), 3 * FRAME_S)

    def test_one_slow_round_trip_widens_it(self):
        steady = playout(rtts=[0.01] * 40).lead(); spike = playout(rtts=[0.01] * 39 + [0.3]).lead()
        self.assertGreater(spike, steady + 0.1)

    def test_it_grows_with_the_link_jitter(self):
        calm = playout(rtts=[0.01] * 20).lead()
        rng = random.Random(1); jittery = playout(rtts=[rng.uniform(0.005, 0.23) for _ in range(40)]).lead()
        self.assertGreater(jittery, calm + 0.1)

    def test_it_never_passes_what_the_client_can_hold(self):
        self.assertAlmostEqual(playout(rtts=[0.01] * 10 + [2.0] * 10).lead(), 0.4 * 0.75)
        self.assertLessEqual(playout(rtts=[0.01] * 10 + [2.0] * 10, capacity=0.2).lead(), 0.2 * 0.75 + 1e-9)


class Hold(unittest.TestCase):
    def test_before_any_reply_is_timed_it_uses_the_prior(self):
        self.assertEqual(playout().hold(), PRIOR_HOLD_S)
        self.assertEqual(playout(max_hold=0.5).hold(), 0.5)

    def test_a_model_faster_than_speech_needs_almost_no_hold(self):
        self.assertAlmostEqual(playout(replies=[(20.0, 10.0)] * 4).hold(), 2 * FRAME_S)

    def test_a_slower_model_needs_the_deficit_over_a_usual_reply(self):
        self.assertAlmostEqual(playout(replies=[(10.0, 12.5)] * 4).hold(), 10.0 * (1 - 0.8))

    def test_it_is_capped_by_the_longest_acceptable_wait(self):
        self.assertEqual(playout(replies=[(20.0, 33.0)] * 4).hold(), 4.0)

    def test_a_recent_stall_raises_it_even_for_a_fast_model(self):
        p = playout(replies=[(20.0, 10.0)] * 7); p.observe_stall(1.7); p.observe_reply(20.0, 10.0)
        self.assertAlmostEqual(p.hold(), 1.7)

    def test_a_stall_in_the_reply_in_progress_counts_at_once(self):
        p = playout(replies=[(20.0, 10.0)] * 4); p.observe_stall(2.5)
        self.assertAlmostEqual(p.hold(), 2.5)

    def test_old_stalls_age_out(self):
        p = playout(replies=[(20.0, 10.0)] * 4); p.observe_stall(3.0); p.observe_reply(20.0, 10.0)
        self.assertGreater(p.hold(), 2.9)
        for _ in range(8): p.observe_reply(20.0, 10.0)
        self.assertAlmostEqual(p.hold(), 2 * FRAME_S)

    def test_a_cancelled_reply_teaches_nothing_but_clears_the_stall(self):
        p = playout(replies=[(20.0, 10.0)] * 4); p.observe_stall(2.0); p.observe_reply(5.0, 50.0, cancelled=True)
        self.assertEqual(len(p.speed), 4); self.assertAlmostEqual(p.hold(), 2 * FRAME_S)

    def test_link_jitter_is_added(self):
        quiet = playout(replies=[(20.0, 10.0)] * 4).hold()
        rng = random.Random(2); noisy = playout(rtts=[rng.uniform(0.005, 0.23) for _ in range(40)], replies=[(20.0, 10.0)] * 4).hold()
        self.assertGreater(noisy, quiet + 0.1)

    def test_a_new_link_forgets_the_old_rtts(self):
        p = playout(rtts=[0.005, 0.3] * 10); p.new_link()
        self.assertAlmostEqual(p.lead(), 0.2)


class Gain(unittest.TestCase):
    def feed(self, g, speech, room=0.002, seconds=6):
        for _ in range(seconds):
            for i in range(50): g.observe(speech if i % 2 else room)
            g.update()
        return g.gain

    def test_quiet_speech_is_raised_toward_the_reference_level(self):
        self.assertAlmostEqual(self.feed(InputGain(), 0.03, seconds=40), 0.1 / 0.03, delta=0.3)

    def test_loud_speech_is_left_alone(self):
        self.assertEqual(self.feed(InputGain(), 0.3), 1.0)

    def test_the_gain_has_a_ceiling(self):
        self.assertAlmostEqual(self.feed(InputGain(max_gain=4.0), 0.01, seconds=60), 4.0, delta=0.05)

    def test_a_room_with_no_speech_leaves_the_gain_alone(self):
        g = InputGain(); g.gain = 3.0
        for _ in range(100): g.observe(0.002)
        self.assertEqual(g.update(), 3.0)

    def test_it_moves_gradually(self):
        g = InputGain()
        for i in range(100): g.observe(0.03 if i % 2 else 0.002)
        first = g.update()
        self.assertGreater(first, 1.0); self.assertLess(first, 0.1 / 0.03)


if __name__ == "__main__":
    unittest.main()
