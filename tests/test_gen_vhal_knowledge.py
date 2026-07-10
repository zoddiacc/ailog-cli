"""Tests for the VHAL knowledge generator tool (tools/gen_vhal_knowledge.py)."""

import importlib.util
import os
import unittest

_TOOL = os.path.join(os.path.dirname(__file__), '..', 'tools', 'gen_vhal_knowledge.py')
_spec = importlib.util.spec_from_file_location('gen_vhal_knowledge', _TOOL)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


# A minimal slice of VehicleProperty.aidl in the real format.
AIDL = '''
@VintfStability
@Backing(type="int")
enum VehicleProperty {
    INVALID = 0x00000000,
    /**
     * VIN of vehicle
     *
     * Requires permission: Car.PERMISSION_IDENTIFICATION.
     *
     * @change_mode VehiclePropertyChangeMode.STATIC
     * @access VehiclePropertyAccess.READ
     */
    INFO_VIN = 0x0100 + 0x10000000,
    /**
     * Current gear. In non-manual case, selected gear may not
     * match the current gear.
     *
     * Requires permission: Car.PERMISSION_POWERTRAIN.
     *
     * @change_mode VehiclePropertyChangeMode.ON_CHANGE
     * @access VehiclePropertyAccess.READ
     */
    CURRENT_GEAR = 0x0401 + 0x10000000,
}
'''


class TestParse(unittest.TestCase):
    def setUp(self):
        self.rows = list(gen.parse(AIDL))
        self.by_name = {r[0]: r for r in self.rows}

    def test_skips_invalid_member(self):
        self.assertNotIn('INVALID', self.by_name)

    def test_extracts_expected_properties(self):
        self.assertIn('INFO_VIN', self.by_name)
        self.assertIn('CURRENT_GEAR', self.by_name)

    def test_access_change_permission_parsed(self):
        name, access, change, perm, summary = self.by_name['INFO_VIN']
        self.assertEqual(access, 'READ')
        self.assertEqual(change, 'STATIC')
        self.assertEqual(perm, 'Car.PERMISSION_IDENTIFICATION')
        self.assertIn('VIN', summary)

    def test_to_entry_is_valid_python_dict_line(self):
        line = gen.to_entry(*self.by_name['CURRENT_GEAR'])
        # It should eval as a dict when wrapped
        d = eval('{' + line.strip() + '}')  # noqa: S307 - trusted generated text
        self.assertIn('CURRENT_GEAR', d)
        short, guidance = d['CURRENT_GEAR']
        self.assertIn('PERMISSION_POWERTRAIN', guidance)
        self.assertIn('READ', guidance)


if __name__ == '__main__':
    unittest.main()
