from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Dict
from google.cloud.firestore import Client as FirestoreClient
from firebase_admin import firestore as fb_admin
from pydantic import BaseModel

from models import User
from routes.auth_routes import get_current_user
from utils.firebase import get_db

router = APIRouter(prefix="/friends", tags=["friends"])

class FriendRequestPayload(BaseModel):
    target_user_id: str

class RespondRequestPayload(BaseModel):
    requester_user_id: str

@router.post(
    "/request",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Відправити запит в друзі"
)
async def send_friend_request(
    payload: FriendRequestPayload,
    current: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    if payload.target_user_id == current.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot send request to yourself")

    target_ref = db.collection("users").document(payload.target_user_id)
    if not target_ref.get().exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target user not found")

    # Перевірка що ми не друзі
    if payload.target_user_id in current.friends:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Already friends")

    # Перевірка, що запит ще не надсилався
    if payload.target_user_id in current.friend_requests_sent:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Request already sent")

    # Перевірка, що нам не надсилали зустрічний запит (можна відразу прийняти)
    if payload.target_user_id in current.friend_requests_received:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "User has already sent you a request")

    # Додаємо в target_user.received і в current.sent
    target_ref.update({
        "friend_requests_received": fb_admin.ArrayUnion([current.user_id])
    })
    db.collection("users").document(current.user_id).update({
        "friend_requests_sent": fb_admin.ArrayUnion([payload.target_user_id])
    })


@router.get(
    "/requests",
    response_model=Dict[str, List[str]],
    summary="Переглянути вхідні та вихідні запити"
)
async def list_friend_requests(
    current: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    me = db.collection("users").document(current.user_id).get().to_dict() or {}
    return {
        "incoming": me.get("friend_requests_received", []),
        "outgoing": me.get("friend_requests_sent", [])
    }


@router.post(
    "/accept",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Прийняти запит в друзі"
)
async def accept_friend_request(
    payload: RespondRequestPayload,
    current: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    requester_id = payload.requester_user_id
    me_ref = db.collection("users").document(current.user_id)
    me_data = me_ref.get().to_dict() or {}
    if requester_id not in me_data.get("friend_requests_received", []):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No such incoming request")

    # Додаємо в friends і видаляємо запити
    me_ref.update({
        "friends":                 fb_admin.ArrayUnion([requester_id]),
        "friend_requests_received": fb_admin.ArrayRemove([requester_id])
    })
    other_ref = db.collection("users").document(requester_id)
    other_ref.update({
        "friends":             fb_admin.ArrayUnion([current.user_id]),
        "friend_requests_sent": fb_admin.ArrayRemove([current.user_id])
    })


@router.post(
    "/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Відхилити запит в друзі"
)
async def reject_friend_request(
    payload: RespondRequestPayload,
    current: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    requester_id = payload.requester_user_id
    me_ref = db.collection("users").document(current.user_id)
    me_data = me_ref.get().to_dict() or {}
    if requester_id not in me_data.get("friend_requests_received", []):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No such incoming request")

    # Видалення тільки запити, не додаючи в друзі
    me_ref.update({
        "friend_requests_received": fb_admin.ArrayRemove([requester_id])
    })
    db.collection("users").document(requester_id).update({
        "friend_requests_sent": fb_admin.ArrayRemove([current.user_id])
    })


@router.delete(
    "/requests/{target_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Скасувати надісланий запит в друзі"
)
async def cancel_friend_request(
    target_user_id: str,
    current: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    if target_user_id == current.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot cancel request to yourself")

    me_ref = db.collection("users").document(current.user_id)
    me_data = me_ref.get().to_dict() or {}
    if target_user_id not in me_data.get("friend_requests_sent", []):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No pending request to this user")

    # Видалення зі своїх відправлених і з його вхідних
    me_ref.update({
        "friend_requests_sent": fb_admin.ArrayRemove([target_user_id])
    })
    db.collection("users").document(target_user_id).update({
        "friend_requests_received": fb_admin.ArrayRemove([current.user_id])
    })


@router.get(
    "",
    response_model=List[User],
    summary="Список друзів поточного користувача"
)
async def list_friends(
    current: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    me = db.collection("users").document(current.user_id).get().to_dict() or {}
    friends_ids = me.get("friends", [])
    friends = []
    for fid in friends_ids:
        snap = db.collection("users").document(fid).get()
        if snap.exists:
            data = snap.to_dict()
            data["user_id"] = fid
            friends.append(User.model_validate(data))
    return friends


@router.delete(
    "/{friend_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Видалити друга"
)
async def remove_friend(
    friend_id: str,
    current: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    me_ref = db.collection("users").document(current.user_id)
    me_data = me_ref.get().to_dict() or {}
    if friend_id not in me_data.get("friends", []):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Friend not found")

    # Видалення з обох списків друзів
    me_ref.update({
        "friends": fb_admin.ArrayRemove([friend_id])
    })
    db.collection("users").document(friend_id).update({
        "friends": fb_admin.ArrayRemove([current.user_id])
    })


@router.get(
    "/search",
    response_model=List[User],
    summary="Пошук користувачів за ніком"
)
async def search_users_by_username(
    username: str = Query(..., min_length=1, description="Фрагмент або повний ніку"),
    current: User = Depends(get_current_user),
    db: FirestoreClient = Depends(get_db),
):
    start = username
    end = username + "\uf8ff"
    snaps = (
        db.collection("users")
          .where("username", ">=", start)
          .where("username", "<=", end)
          .stream()
    )

    results = []
    for doc in snaps:
        if doc.id == current.user_id:
            continue
        data = doc.to_dict()
        data["user_id"] = doc.id
        results.append(User.model_validate(data))
    return results
