"""Local comparison must preserve changes and not become a loop oracle."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.loop.local_text_similarity import compare, token_vector


class LocalComparisonTests(unittest.TestCase):
    def test_input_changes_survive_tokenization(self):
        self.assertNotEqual(token_vector('answer = 2'),token_vector('answer = 3'))
        self.assertNotEqual(token_vector('Value'),token_vector('value'))
        self.assertNotEqual(token_vector('send the request'),token_vector('do not send the request'))

    def test_high_similarity_does_not_assert_meaning_or_repetition(self):
        result=compare('send the request','do not send the request')
        self.assertFalse(result['nonempty_identical'])
        self.assertGreater(result['lexical_token_cosine'],0)
        self.assertNotIn('loop',result)
        self.assertNotIn('semantically_equal',result)

    def test_lexical_order_collision_is_visible_in_exact_comparison(self):
        result=compare('Alice follows Bob','Bob follows Alice')
        self.assertAlmostEqual(result['lexical_token_cosine'],1)
        self.assertFalse(result['nonempty_identical'])

    def test_layout_noise_and_empty_input(self):
        self.assertTrue(compare('one\n two','one two')['nonempty_identical'])
        empty=compare('','')
        self.assertFalse(empty['nonempty_identical'])
        self.assertIsNone(empty['lexical_token_cosine'])


if __name__=='__main__':
    unittest.main()
