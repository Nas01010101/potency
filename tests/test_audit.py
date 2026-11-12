from potency import audit

PATCH = """--- a/m.py
+++ b/m.py
@@ -1,3 +1,3 @@ def trim(s):
-    return s
+    return s.strip()
+def helper(x):
"""


def test_names_reads_hunk_headers_and_changed_defs():
    assert audit.names(PATCH) == ['helper', 'trim']


def test_excerpt_windows_and_fallback():
    text = '\n'.join(['a', 'b', 'x = trim(y)', 'c', 'd', 'e', 'f', 'g', 'h'])
    assert audit.excerpt(text, ['trim'], ctx=1) == '2: b\n3: x = trim(y)\n4: c'
    assert audit.excerpt(text, ['nope']).startswith('(none of the changed names')


def test_parse_verdicts():
    assert audit.parse('DOUBT: it calls trim and relies on old output') == ('DOUBT', 'it calls trim and relies on old output')
    assert audit.parse('**HOLDS** - unrelated') == ('HOLDS', 'unrelated')
    assert audit.parse('maybe')[0] == 'UNPARSED'
