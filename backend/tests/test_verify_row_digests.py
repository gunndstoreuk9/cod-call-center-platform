import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scripts.verify_row_digests import classify, digest, parse_rows, summarize  # noqa: E402

KEY = 'unit-test-key'


def test_digest_is_format_independent_and_not_a_phone():
    assert digest(KEY, '0612345678') == digest(KEY, '+212 612-345-678') == digest(KEY, '612345678')
    assert '612345678' not in digest(KEY, '0612345678')


def test_1046_scenario_confirms_owner_flags_false_imported_and_keeps_legit_orders():
    orders = [  # what CODOPS holds
        {'order_number': 'CC-A', 'external_order_id': '1046', 'phone': '+212611110006', 'sku': 'NOVAMAN2026'},
        {'order_number': 'CC-B', 'external_order_id': '1047', 'phone': '+212644440007', 'sku': 'NOVAMAN2026'},
        {'order_number': 'CC-C', 'external_order_id': 'fp:abc', 'phone': '+212677770011', 'sku': 'NOVAMAN2026'},
    ]
    d = lambda p: digest(KEY, p)
    text = 'noise\nDIGESTS_BEGIN\nrow|ext|status|orderNo|sku|qty|total|digest\n' + '\n'.join([
        f'113|1046|IMPORTED|CC-A|NOVAMAN2026|1|199|{d("0611110006")}',   # owner
        f'154|1046|IMPORTED|CC-A|NOVAMAN2026|1|199|{d("0622220099")}',   # false duplicate of CC-A
        f'155|1046|IMPORTED|CC-A|NOVAMAN2026|1|199|{d("0633330098")}',   # false duplicate of CC-A
        f'120|1047|IMPORTED||NOVAMAN2026|1|199|{d("0644440007")}',       # real order, sheet mark missing
        f'130|9999|IMPORTED||NOVAMAN2026|1|199|{d("0677770011")}',       # same customer+SKU under another id
        f'131|2000||||1|199|{d("0688880001")}',                           # never imported, SKU empty
        '132|2001|IMPORTED||NOVAMAN2026|1|199|NOPHONE',
    ]) + '\nDIGESTS_END\n'
    rows = parse_rows(text)
    assert len(rows) == 7
    res = {r['row']: r for r in classify(rows, orders, {'NOVAMAN2026'}, KEY)}
    assert res[113]['verdict'] == 'CONFIRMED_OWN'
    assert res[154]['verdict'] == res[155]['verdict'] == 'NUMBER_BELONGS_TO_OTHER'
    assert res[120]['verdict'] == 'OWNER_BY_EXT_ID' and res[120]['found_order'] == 'CC-B'
    assert res[130]['verdict'] == 'POSSIBLE_EXISTING'          # phone+SKU match alone => review, never "missing"
    assert res[131]['verdict'] == 'NO_ORDER_FOUND'
    assert res[132]['verdict'] == 'NO_PHONE'
    sm = summarize(list(res.values()))
    assert sm['confirmed_missing_rows'] == [131, 154, 155]
    assert sm['confirmed_missing_importable_now'] == [154, 155]
    assert sm['confirmed_missing_blocked_by_sku'] == [131] and sm['blocked_sku_values'] == ['(empty)']
