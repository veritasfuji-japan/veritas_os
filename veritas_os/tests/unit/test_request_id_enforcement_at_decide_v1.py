from types import SimpleNamespace
import hashlib, json, pytest
from veritas_os.core.pipeline.pipeline_inputs import normalize_pipeline_inputs

PROFILE="veritas.rveval.request-id-derivation/v1"
PREFIX="rveval-request:v1:sha256:"

class Req:
    def __init__(self, body): self.body=body
    def model_dump(self): return dict(self.body)

def rid(body):
    request={k:body[k] for k in ("query","context","alternatives","min_evidence","memory_auto_put","persona_evolve")}
    raw=json.dumps({"profile":PROFILE,"request":request},ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    return PREFIX+hashlib.sha256(raw).hexdigest()

def body():
    b={"query":"original request A","context":{"original_request_digest":"sha256:"+"a"*64},
       "alternatives":[{"id":"c1","title":"candidate"}],"min_evidence":1,
       "memory_auto_put":False,"persona_evolve":False,"request_id_profile":PROFILE}
    b["request_id"]=rid(b); return b

def norm(b):
    request=SimpleNamespace(state=SimpleNamespace(authenticated_principal_id=None),query_params={},params={})
    return normalize_pipeline_inputs(Req(b),request,_get_request_params=lambda _: {},_to_dict_fn=lambda x:x)

def test_matching_content_bound_id_is_accepted(): assert norm(body()).request_id==body()["request_id"]

@pytest.mark.parametrize("mutator",[
 lambda b:b.__setitem__("query","original request B"),
 lambda b:b["context"].__setitem__("original_request_digest","sha256:"+"b"*64),
 lambda b:b["alternatives"][0].__setitem__("id","c2"),
 lambda b:b.__setitem__("min_evidence",2),
])
def test_stale_id_fails_closed_before_pipeline(mutator):
    b=body(); mutator(b)
    with pytest.raises(ValueError,match="REQUEST_ID_CONTENT_MISMATCH"): norm(b)

def test_swapped_bound_id_fails_closed():
    b=body(); b["request_id"]=PREFIX+"f"*64
    with pytest.raises(ValueError,match="REQUEST_ID_CONTENT_MISMATCH"): norm(b)

def test_legacy_request_id_remains_compatible():
    b={"query":"legacy","context":{},"alternatives":[{"id":"x"}],"request_id":"legacy-id"}
    assert norm(b).request_id=="legacy-id"
