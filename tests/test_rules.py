from yaku.classify import is_passthrough
from yaku.masking import Masker


def order_of(rules):
    return {rule.name: rule.order for rule in rules}


def test_bracket_is_evaluated_first(mask_rules):
    orders = order_of(mask_rules)
    assert orders["BRACKET"] == min(orders.values())


def test_cfgkey_is_evaluated_before_ident(mask_rules):
    orders = order_of(mask_rules)
    assert orders["CFGKEY"] < orders["IDENT"]


def test_compare_is_enabled(mask_rules):
    assert next(r for r in mask_rules if r.name == "COMPARE").enabled


def test_version_is_disabled(mask_rules):
    assert not next(r for r in mask_rules if r.name == "VERSION").enabled


def test_bracket_contents_are_masked_as_one_value(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    masked, values = masker.mask('aws_instance.web will be created [id=A|B|"PUBLIC"]')
    assert '[id=A|B|"PUBLIC"]' in values
    assert "PUBLIC" not in masked


def test_config_key_survives_as_one_value(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    _masked, values = masker.mask("zstd:frame-per-file is supported.")
    assert values == ["zstd:frame-per-file"]


def test_comparison_operator_is_masked(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    _masked, values = masker.mask("The program exits >0 if an error occurs.")
    assert ">0" in values


def test_shipped_rules_round_trip(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    for line in [
        "Use -cftuvSUX with --format ustar to write archives.",
        "Checkout 'origin/main' before you continue.",
        "See tar(1) and environ(7) for details.",
    ]:
        masked, values = masker.mask(line)
        assert masker.unmask(masked, values) == line


def test_progress_rule_ignores_prose(passthrough):
    assert not is_passthrough("Note: Reading the archive is slower than writing it.", passthrough)
    assert not is_passthrough(
        "Warning: Creating a sparse file may fail on some systems.", passthrough
    )


def test_progress_rule_matches_a_resource_address(passthrough):
    assert is_passthrough("aws_instance.web: Refreshing state...", passthrough)
    assert is_passthrough("module.vpc.aws_subnet.private: Creating...", passthrough)


def test_hyphenated_name_is_masked_whole(mask_rules, japanese):
    """A hex segment inside a longer name must not be taken on its own: the
    identifier rule cannot match across a placeholder, so the rest of the
    name would reach the model unprotected."""
    masker = Masker(rules=mask_rules, target=japanese)
    masked, values = masker.mask("The pod payment-worker-7d9f8b6c5-xk2lp is pending.")
    assert "payment-worker-7d9f8b6c5-xk2lp" in values
    assert "payment-worker" not in masked


def test_standalone_hash_is_still_masked(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    _, values = masker.mask("Commit 9f8b6c5a1d2e3f4 was reverted.")
    assert "9f8b6c5a1d2e3f4" in values


def test_terraform_diagnostic_lines_pass_through(passthrough):
    for line in [
        "  15:   content  = local.missing_value",
        '   6: variable "env" {',
        "    ├────────────────",
        '    │ var.env is "qa"',
    ]:
        assert is_passthrough(line, passthrough), line


def test_diagnostic_rules_ignore_manual_prose(passthrough):
    for line in [
        "     1.   The first argument is the archive name.",
        "     Step 2: extract the files into the current directory.",
        "     Version 3 of the format adds support for long names.",
    ]:
        assert not is_passthrough(line, passthrough), line


def test_kubectl_example_invocations_pass_through(passthrough):
    for line in [
        "  kubectl describe pods",
        "  kubectl describe pods frontend",
        "  kubectl describe nodes kubernetes-node-emt8.c.myproject.internal",
    ]:
        assert is_passthrough(line, passthrough), line


def test_kubectl_example_rule_ignores_prose(passthrough):
    for line in [
        "kubectl controls the Kubernetes cluster manager.",
        "kubectl describe will first check for an exact match",
        "kubectl uses the current context by default",
    ]:
        assert not is_passthrough(line, passthrough), line


def test_describe_fields_pass_through(passthrough):
    for line in [
        "Name:         nginx-deployment-67d4bdd6f5-w6kd7",
        "    Restart Count:  0",
        "  Controlled By:  ReplicaSet/nginx-deployment-67d4bdd6f5",
        "  Namespace:\tdefault",
        "    Type:                    Projected (a volume that contains injected data)",
    ]:
        assert is_passthrough(line, passthrough), line


def test_table_header_passes_through(passthrough):
    for line in [
        "  Type    Reason     Age   From               Message",
        "    FirstSeen\tLastSeen\tCount\tFrom\tType\tReason\tMessage",
    ]:
        assert is_passthrough(line, passthrough), line


def test_field_rules_ignore_prose_with_a_colon(passthrough):
    for line in [
        "     Note: the archive must exist before it can be updated.",
        "     The following options are available: create, list and extract.",
        "Example: tar -cf archive.tar foo",
        "     Keyboard-interactive authentication works as follows: The server",
    ]:
        assert not is_passthrough(line, passthrough), line


def test_sha256_digest_is_masked(mask_rules, japanese):
    digest = "5403af59a2b46ee5a23fb0ae4b1e077f7ca5c5fb7af16e1ab21c00e0e616462a"
    _, values = Masker(rules=mask_rules, target=japanese).mask(f"The container {digest} restarted.")
    assert digest in values


def test_describe_mounts_and_taints_pass_through(passthrough):
    for line in [
        "      /var/run/secrets/kubernetes.io/serviceaccount from kube-api-access-bgsgp (ro)",
        "                             node.kubernetes.io/unreachable:NoExecute op=Exists for 300s",
    ]:
        assert is_passthrough(line, passthrough), line


def test_tree_output_passes_through(passthrough):
    for line in ["├── src", "│   └── yaku", "└── README.md"]:
        assert is_passthrough(line, passthrough), line


def test_diagnostic_subject_line_passes_through(passthrough):
    for line in [
        "│   with aws_s3_bucket.ceph,".removeprefix("│"),
        "  with module.net.aws_subnet.private[0],",
    ]:
        assert is_passthrough(line, passthrough), line
    assert not is_passthrough("  with the archive open, list its contents,", passthrough)
