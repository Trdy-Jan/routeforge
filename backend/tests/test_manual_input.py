from routeforge.parsers.manual import parse_manual_input

SINGLE = "name: M\ntype: mieru\nserver: 203.0.113.10\nport: 1\ntransport: TCP\nusername: u\npassword: p\n"


def test_single_mapping():
    assert [n.name for n in parse_manual_input(SINGLE).nodes] == ["M"]


def test_bare_list_with_one_bad_item():
    text = "- " + SINGLE.replace("\n", "\n  ").rstrip() + "\n- {name: X, type: snell, server: a, port: 1}\n"
    out = parse_manual_input(text)
    assert [n.name for n in out.nodes] == ["M"]
    assert out.errors[0].line == "X" and "snell" in out.errors[0].message


def test_proxies_document_and_links_still_work():
    assert len(parse_manual_input("proxies:\n  - " + SINGLE.replace("\n", "\n    ")).nodes) == 1
    assert len(parse_manual_input("mierus://u:p@h?profile=d&port=1&protocol=TCP").nodes) == 1


def test_plain_garbage_reports_error():
    out = parse_manual_input("hello world")
    assert out.nodes == [] and out.errors


def test_bare_list_with_non_mapping_item_keeps_good_nodes():
    text = "- " + SINGLE.replace("\n", "\n  ").rstrip() + "\n- foo\n- {name: NoType, server: a, port: 1}\n"
    out = parse_manual_input(text)
    assert [n.name for n in out.nodes] == ["M"]
    assert len(out.errors) == 2


def test_input_without_any_node_reports_error():
    out = parse_manual_input("# ss://comment-only")
    assert out.nodes == [] and out.errors[0].message == "没有识别到任何节点"
