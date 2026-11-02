from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/operator", tags=["operator"])


@router.post("/classrooms/{classroomId}/simulator/faults", status_code=201)
async def inject_fault(classroomId: str) -> dict[str, Any]:
    return {
        "id": "",
        "device_id": "",
        "kind": "unavailable",
        "active": True,
        "created_at": "",
        "expires_at": None,
        "created_by": "",
    }


@router.get("/classrooms/{classroomId}/simulator/faults")
async def list_faults(classroomId: str) -> dict[str, Any]:
    return {"items": []}


@router.delete("/simulator/faults/{faultId}")
async def delete_fault(faultId: str) -> dict[str, Any]:
    return {"active": False}


@router.post("/classrooms/{classroomId}/simulator/occupancy")
async def set_occupancy(classroomId: str) -> dict[str, Any]:
    return {
        "device_id": "D11",
        "state": {"motion": "not_detected"},
        "presence_minutes": 0,
        "state_version": 0,
    }


@router.post("/classrooms/{classroomId}/simulator/reset")
async def reset_simulator(classroomId: str) -> dict[str, Any]:
    return {
        "restored": True,
        "state_version": 0,
        "restored_devices": 0,
        "faults_cleared": 0,
        "initial_state_ref": "seed-42",
    }


@router.get("/classrooms/{classroomId}/adapter/health")
async def adapter_health(classroomId: str) -> dict[str, Any]:
    return {"adapter": "simulator", "status": "ok", "checked_at": None, "devices": []}


@router.get("/summary")
async def summary(window: str = "1h") -> dict[str, Any]:
    return {
        "runs": {"applied": 0, "failed": 0, "running": 0, "partial": 0},
        "adapter": {"p95_read_ms": 0, "p95_execute_ms": 0, "status": "ok"},
        "errors": [],
        "voice": {"actions_total": 0, "success_rate": 0.0},
        "energy": {"devices_off_after_finish": 0, "estimated_watts_saved": 0},
    }
