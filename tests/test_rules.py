from yaku.classify import is_passthrough, looks_like_command
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


def test_table_rows_with_narrow_or_tabbed_columns_pass_through(passthrough):
    for line in [
        "exclude      -             Exclude a file from the transfer",
        "  1m\t\t    48s\t\t    7\t    {default-scheduler }\t\t\tWarning\t\tFailedScheduling",
        "  Tue, 03 May 2016 12:43:38 -0700    Tue, 03 May 2016 13:38:54 -0700    25",
        "Image(s):            ecr.example.com/spark:dev",
    ]:
        assert is_passthrough(line, passthrough), line


def test_option_description_with_one_gap_is_not_a_table(passthrough):
    assert not is_passthrough(
        "     -c      Create a new archive containing the specified items.", passthrough
    )


def test_prompts_and_embedded_scripts_are_commands():
    for line in [
        "root@nm:/work-place/kubernetes# kubectl describe pod coredns -n kube-system",
        "➜  ~ kubectl describe pods test-pod",
        "% git config set core.filemode true",
        "if [ ! -f /work/first_run_done ]; then",
        'echo "First run: creating marker and exiting with 1."',
        "fi",
    ]:
        assert looks_like_command(line), line


def test_prose_with_quotes_or_percent_is_not_a_command():
    for line in [
        'curl does not parse or otherwise "understand" the content it gets or',
        'git rebase will stop when "pick" has been replaced with "edit" or when a',
        "% you just write them as %%. You can output a newline by using",
    ]:
        assert not looks_like_command(line), line


def test_zsh_prompt_with_user_and_host_is_a_command():
    assert looks_like_command("thomas@ninox ~ % aws --debug sqs list-queues")


def test_quoted_span_is_masked_whole(mask_rules, japanese):
    masked, values = Masker(rules=mask_rules, target=japanese).mask('the "old --force mode" flag')
    assert masked == "the T1 flag"
    assert values == ['"old --force mode"']


def test_quoted_span_keeps_path_and_spacing_inside(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    masked, values = masker.mask('run "copy  /etc/hosts  now" first')
    assert masked == "run T1 first"
    assert values == ['"copy  /etc/hosts  now"']


def test_apostrophes_do_not_open_a_quoted_span(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    masked, values = masker.mask("Don't use 'config' while the user's file is open.")
    assert values == ["'config'"]
    assert masked.startswith("Don't use T1 while")


def test_quoted_span_allows_other_quote_types_inside(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    _, values = masker.mask('say "can\'t  stop now" twice')
    assert values == ['"can\'t  stop now"']


def test_index_quote_stays_in_its_terraform_address(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    _, values = masker.mask('module.x.aws_s3_bucket.b["logs"] will be created')
    assert values == ['module.x.aws_s3_bucket.b["logs"]']


def test_stack_frame_rule_ignores_wrapped_prose(passthrough):
    assert not is_passthrough("from the given files and directories.", passthrough)
    assert not is_passthrough("at least one archive must be named.", passthrough)


def test_stack_frame_rule_matches_frames(passthrough):
    assert is_passthrough("    at com.example.Main.run(Main.java:12)", passthrough)
    assert is_passthrough('  File "/app/main.py", line 3, in <module>', passthrough)
    assert is_passthrough("    at /app/index.js:10:5", passthrough)


def test_single_component_absolute_path_is_masked(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    masked, values = masker.mask("The files are stored in /tmp.")
    assert values == ["/tmp"]
    assert masked == "The files are stored in T1."


def test_slash_inside_a_word_is_not_a_path(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    assert masker.mask("Use read/write access and/or I/O.")[1] == []


def test_literal_placeholder_text_inside_enclosing_spans_is_protected(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    for text in ('say "T1 ready" now', "see /etc/T1/config now", 'say "hello  [world]  now" now'):
        masked, values = masker.mask(text)
        assert masked == text.replace(values[0], "T1")
        assert masker.unmask(masked, values) == text


def test_skipped_glued_match_leaves_existing_placeholders_intact(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    masked, values = masker.mask("Read config/T2/file before starting.")
    assert masker.unmask(masked, values) == "Read config/T2/file before starting."


def test_touching_matches_become_one_value(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    for text in ("Read the [first][second] entries now.", 'Use "a b""c d" as the value.'):
        masked, values = masker.mask(text)
        assert len(values) == 1
        assert masker.unmask(masked, values) == text
        assert masker.lost(masked, len(values)) == 0


def test_words_that_resemble_placeholders_are_not_damage(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    text = "The ext4 filesystem is supported with --force."
    masked, values = masker.mask(text)
    translated = masked.replace("is supported", "に対応")
    assert masker.residue(translated, len(values), masked) == 0
    assert masker.residue(translated, len(values)) == 1
    assert masker.unmask(masked, values) == text


def test_source_word_is_recognised_next_to_japanese_text(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    masked, values = masker.mask("The ext4 filesystem is supported with --force.")
    translated = "ext4ファイルシステムはT1に対応しています。"
    assert masker.residue(translated, len(values), masked) == 0


def test_long_quoted_literal_is_masked_whole(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    quoted = '"' + "connection  refused by the remote server while opening the stream " * 2 + '"'
    _, values = masker.mask(f"The message {quoted} is printed.")
    assert values == [quoted]


def test_terraform_index_keys_are_part_of_the_address(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    for address in (
        'module.x.aws_s3_bucket.b["logs/archive"]',
        'aws_instance.web["a key"]',
        "aws_instance.web[0]",
    ):
        _, values = masker.mask(f"{address} will be created")
        assert values == [address]


def test_index_key_that_looks_like_a_path_stays_inside_the_address(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    for address in (
        'module.storage.aws_s3_bucket.logs["/archive/2026"]',
        'aws_s3_bucket.logs["/archive/2026"]',
    ):
        masked, values = masker.mask(f"{address} will be created")
        assert values == [address]
        assert masked == "T1 will be created"
