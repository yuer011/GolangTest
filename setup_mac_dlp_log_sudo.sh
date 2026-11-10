#!/bin/sh
set -eu

RULE_FILE="/etc/sudoers.d/corplink-dlp-auto-edlp-log"

usage() {
    cat <<'EOF'
Usage:
  scripts/setup_mac_dlp_log_sudo.sh          Preview the sudoers rule
  scripts/setup_mac_dlp_log_sudo.sh --apply  Validate and install the rule
  scripts/setup_mac_dlp_log_sudo.sh --check  Verify sudo + bread without log output
  scripts/setup_mac_dlp_log_sudo.sh --remove Remove the installed rule

Run this script as the normal login user. It invokes sudo only for installing
or removing one sudoers.d file.
EOF
}

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

if [ "$#" -gt 1 ]; then
    usage
    exit 2
fi

mode="${1:-preview}"
case "$mode" in
    preview|--apply|--check|--remove) ;;
    -h|--help)
        usage
        exit 0
        ;;
    *)
        usage
        exit 2
        ;;
esac

if [ "$(id -u)" -eq 0 ]; then
    fail "do not run the whole script with sudo; run it as the login user"
fi

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
config_path="$repo_root/config/config.yaml"

[ -f "$config_path" ] || fail "config not found: $config_path"

read_mac_scalar() {
    key=$1
    awk -v key="$key" '
        /^verify:[[:space:]]*$/ {
            in_verify = 1
            next
        }
        in_verify && /^[^[:space:]#]/ {
            in_verify = 0
        }
        in_verify && /^  dlp_log:[[:space:]]*$/ {
            in_dlp_log = 1
            next
        }
        in_dlp_log && /^  [^[:space:]#]/ {
            in_dlp_log = 0
            in_mac = 0
        }
        in_dlp_log && /^    mac:[[:space:]]*$/ {
            in_mac = 1
            next
        }
        in_mac && /^    [^[:space:]#]/ {
            in_mac = 0
        }
        in_mac && index($0, "      " key ":") == 1 {
            value = $0
            sub("^      " key ":[[:space:]]*", "", value)
            sub(/[[:space:]]+#.*$/, "", value)
            if (value ~ /^".*"$/ || value ~ /^\047.*\047$/) {
                value = substr(value, 2, length(value) - 2)
            }
            paths[++count] = value
        }
        END {
            if (count != 1 || paths[1] == "") {
                exit 1
            }
            print paths[1]
        }
    ' "$config_path"
}

log_path=$(read_mac_scalar path) ||
    fail "cannot read exactly one verify.dlp_log.mac.path from $config_path"
decoder_value=$(read_mac_scalar decoder) ||
    fail "cannot read exactly one verify.dlp_log.mac.decoder from $config_path"
event_category=$(read_mac_scalar event_category) ||
    fail "cannot read exactly one verify.dlp_log.mac.event_category from $config_path"
event_marker=$(read_mac_scalar event_marker) ||
    fail "cannot read exactly one verify.dlp_log.mac.event_marker from $config_path"

case "$log_path" in
    *[!A-Za-z0-9_./-]*)
        fail "log path contains characters unsupported by this sudoers helper"
        ;;
esac

case "$log_path" in
    /*) ;;
    *) fail "verify.dlp_log.mac.path must be absolute: $log_path" ;;
esac

case "$decoder_value" in
    /*) decoder_path=$decoder_value ;;
    *) decoder_path="$repo_root/$decoder_value" ;;
esac

login_user=$(id -un)
case "$login_user" in
    *[!A-Za-z0-9_.-]*)
        fail "login user contains characters unsupported by this helper"
        ;;
esac

cat_bin=$(command -v cat)
sudo_bin=$(command -v sudo)
visudo_bin=$(command -v visudo)
install_bin=$(command -v install)

rule="$login_user ALL=(root) NOPASSWD: $cat_bin $log_path"

check_pipeline() {
    [ -x "$decoder_path" ] ||
        fail "Mac DLP decoder is not executable: $decoder_path"
    if ! "$sudo_bin" -n "$cat_bin" "$log_path" >/dev/null; then
        fail "the exact sudo read command is not authorized"
    fi

    bread_format=$(printf '%%d\t%%C\t%%m')
    stats=$(
        "$sudo_bin" -n "$cat_bin" "$log_path" |
            "$decoder_path" -f "$bread_format" - |
            awk -F '	' \
                -v category_name="$event_category" \
                -v marker="$event_marker" '
                {
                    total++
                }
                index($2, category_name) {
                    category++
                }
                index($3, "dlp audit event:") == 1 {
                    audit_event++
                }
                index($2, category_name) &&
                    index($3, marker) == 1 {
                    marker_count++
                }
                index($2, category_name) &&
                    index($3, marker) == 1 &&
                    index($3, "\"eventId\"") {
                    event_id++
                }
                END {
                    printf "%d|%d|%d|%d|%d\n",
                        total + 0,
                        category + 0,
                        audit_event + 0,
                        marker_count + 0,
                        event_id + 0
                }
            '
    )
    old_ifs=$IFS
    IFS='|'
    set -- $stats
    IFS=$old_ifs
    [ "$#" -eq 5 ] || fail "cannot parse bread diagnostic counters"
    decoded_lines=$1
    category_lines=$2
    audit_event_lines=$3
    marker_lines=$4
    event_id_lines=$5
    printf '%s\n' \
        "decoded_lines=$decoded_lines" \
        "category_lines=$category_lines" \
        "audit_event_lines=$audit_event_lines" \
        "marker_lines=$marker_lines" \
        "event_id_lines=$event_id_lines"
    [ "$marker_lines" -gt 0 ] && [ "$event_id_lines" -gt 0 ] ||
        fail "bread output does not match the configured DLP event shape"
    printf 'End-to-end check passed.\n'
}

if [ "$mode" = "preview" ]; then
    printf 'Target: %s\n' "$RULE_FILE"
    printf 'Rule:   %s\n' "$rule"
    printf '\nReview it, then run:\n  %s --apply\n' "$0"
    exit 0
fi

if [ "$mode" = "--check" ]; then
    check_pipeline
    exit 0
fi

if [ "$mode" = "--remove" ]; then
    "$sudo_bin" rm -f "$RULE_FILE"
    "$sudo_bin" "$visudo_bin" -c
    printf 'Removed %s\n' "$RULE_FILE"
    exit 0
fi

[ -e "$log_path" ] || fail "Mac DLP log does not exist: $log_path"
[ -d "$(dirname "$RULE_FILE")" ] ||
    fail "sudoers.d directory does not exist: $(dirname "$RULE_FILE")"

tmp_rule=$(mktemp "${TMPDIR:-/tmp}/corplink-dlp-auto-sudoers.XXXXXX")
trap 'rm -f "$tmp_rule"' EXIT HUP INT TERM
printf '%s\n' "$rule" >"$tmp_rule"

"$visudo_bin" -cf "$tmp_rule"
"$sudo_bin" "$install_bin" \
    -o root -g wheel -m 0440 "$tmp_rule" "$RULE_FILE"
"$sudo_bin" "$visudo_bin" -cf "$RULE_FILE"

# Drop any cached sudo ticket so this proves the NOPASSWD rule itself works.
"$sudo_bin" -k
check_pipeline

printf 'Installed and verified: %s\n' "$RULE_FILE"
printf 'Allowed command: sudo -n %s %s\n' "$cat_bin" "$log_path"
