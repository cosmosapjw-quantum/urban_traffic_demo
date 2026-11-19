"""Original exact V03 resumed prefix source/clock budget compatibility checks."""
import copy,hashlib,json
from pathlib import Path
import pytest
from tools.research.continue_original_v03_prefix import validate_start_binding

ROOT=Path(__file__).resolve().parents[2]
PREFIX=ROOT/"artifacts/kcmb_v03_physics_20261119/prefix/valley_weekday_s7.native_23000.json"


def test_original_real_100k_prefix_is_genuine_and_bounded():
    row=json.loads(PREFIX.read_text())
    sha=hashlib.sha256((ROOT/"scenarios/v1/release_matrix.json").read_bytes()).hexdigest()
    result=validate_start_binding(row,
        case="valley_weekday_s7",
        matrix_sha=sha,
        driver_identity=row["driver_identity"],
        native_binary_sha=row["native_binary_sha256"],
        candidate_source_sha=row["candidate_source_sha256"],
        expected_time_s=23000.)
    assert result=="ORIGINAL_V03_PREFIX_BINDING_VERIFIED"
    assert row["status"]=="EXECUTED_FOR_REVIEW"
    assert row["simulated_s"]==23000
    assert row["report"]["calendar"]["calendar"]["resident_stock"]==100000


def test_false_physical_or_source_receipts_fail_explicitly():
    real=json.loads(PREFIX.read_text())
    sha=real["matrix_sha256"]
    kw=dict(case=real["case"],matrix_sha=sha,
        driver_identity=real["driver_identity"],
        native_binary_sha=real["native_binary_sha256"],
        candidate_source_sha=real["candidate_source_sha256"],
        expected_time_s=23000.)
    for key,value in [
        ("matrix_sha256","0"*64),
        ("simulated_s",22000),
        ("status","WHOLE_CALENDAR_PREPARED"),
        ("engine_backend","python_oracle"),
        ("address_space_limit_bytes",9*1024**3),
    ]:
        bad=dict(real);bad[key]=value
        with pytest.raises(ValueError,match="binding|source|resource|prefix"):
            validate_start_binding(bad,**kw)
    with pytest.raises(ValueError,match="binding|source"):
        validate_start_binding(real,**(kw|{"native_binary_sha":"0"*64}))


def test_native_step_clock_is_canonical_float_to_preserve_checkpoint_identity():
    from tools.research.continue_original_v03_prefix import canonical_step_seconds
    # JSON static payloads distinguish 10 from 10.0 despite equal arithmetic.
    # The original CLI args are argparse(type=float), so the raw integer
    # literal previously reconstructed a different native static identity.
    for x in (10, 10.0):
        out=canonical_step_seconds(x)
        assert type(out) is float and out==10.0
    with pytest.raises(ValueError):
        canonical_step_seconds(0)
    with pytest.raises(ValueError):
        canonical_step_seconds(float("nan"))
