"""Tests for src/sleep_monitor.py. Run with: python -m unittest discover tests"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

try:
    import jeepney  # noqa: F401
except ImportError:
    jeepney = None

import sleep_monitor


def prepare_for_sleep_signal(sender):
    from jeepney import DBusAddress, new_signal
    from jeepney.low_level import HeaderFields
    msg = new_signal(DBusAddress(sleep_monitor.LOGIN1_PATH, interface=sleep_monitor.LOGIN1_IFACE),
                     'PrepareForSleep', 'b', (True,))
    msg.header.fields[HeaderFields.sender] = sender
    return msg


@unittest.skipIf(jeepney is None, "jeepney not installed")
class MatchRuleTests(unittest.TestCase):
    def test_local_rule_matches_signal_from_unique_name(self):
        # The bus delivers signals with logind's unique name (e.g. ':1.2') as
        # sender, never 'org.freedesktop.login1'. The local filter must match it.
        _, local_rule = sleep_monitor.build_match_rules()
        self.assertTrue(local_rule.matches(prepare_for_sleep_signal(':1.2')))

    def test_bus_rule_restricts_sender_to_logind(self):
        bus_rule, _ = sleep_monitor.build_match_rules()
        self.assertIn("sender='org.freedesktop.login1'", bus_rule.serialise())

    def test_local_rule_ignores_other_signals(self):
        from jeepney import DBusAddress, new_signal
        _, local_rule = sleep_monitor.build_match_rules()
        other = new_signal(DBusAddress(sleep_monitor.LOGIN1_PATH, interface=sleep_monitor.LOGIN1_IFACE),
                           'PrepareForShutdown', 'b', (True,))
        self.assertFalse(local_rule.matches(other))

    def test_signal_received_over_real_bus(self):
        # End to end through jeepney's dispatch: emit PrepareForSleep on the
        # session bus (sender header = our unique name) and receive it via the
        # same local filter the monitor uses.
        from jeepney import DBusAddress, MatchRule, message_bus, new_signal
        from jeepney.io.blocking import open_dbus_connection, Proxy
        try:
            receiver = open_dbus_connection(bus='SESSION')
            sender = open_dbus_connection(bus='SESSION')
        except Exception as e:
            self.skipTest("no session bus: {}".format(e))
        try:
            _, local_rule = sleep_monitor.build_match_rules()
            # Session bus has no logind, so register by our sender's unique name.
            bus_rule = MatchRule(type='signal', sender=sender.unique_name,
                                 path=sleep_monitor.LOGIN1_PATH,
                                 interface=sleep_monitor.LOGIN1_IFACE, member='PrepareForSleep')
            Proxy(message_bus, receiver).AddMatch(bus_rule)
            with receiver.filter(local_rule) as queue:
                sender.send(new_signal(DBusAddress(sleep_monitor.LOGIN1_PATH,
                                                   interface=sleep_monitor.LOGIN1_IFACE),
                                       'PrepareForSleep', 'b', (True,)))
                msg = receiver.recv_until_filtered(queue, timeout=2)
            self.assertIs(msg.body[0], True)
        finally:
            receiver.close()
            sender.close()


if __name__ == '__main__':
    unittest.main()
