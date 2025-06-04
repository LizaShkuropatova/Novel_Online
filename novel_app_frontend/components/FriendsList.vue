<template>
  <b-container class="py-4">
    <h3 class="mb-3">{{ title }}</h3>

    <!-- Search -->
    <div class="input-group input-group-sm mb-2">
      <input
        v-model="search"
        @input="onSearch"
        type="text"
        class="form-control form-control-sm"
        placeholder="Search by nickname…"
      />
      <b-button size="sm" variant="outline-primary" @click="onSearch">
        <i class="bi-search me-1" /> Search
      </b-button>
    </div>

    <!-- Tabs -->
    <div class="d-flex gap-2 mb-4">
      <b-button
        v-for="tab in tabs"
        :key="tab.value"
        size="sm"
        :variant="activeTab === tab.value ? 'primary' : 'outline-primary'"
        @click="selectTab(tab.value)"
      >
        {{ tab.label }}
      </b-button>
    </div>

    <!-- Список карточек или пусто -->
    <div v-if="displayList.length === 0" class="text-center text-muted">
      Nothing found
    </div>
    <div v-else>
      <FriendCard
        v-for="f in displayList"
        :key="f.user_id"
        :friend="f"
        :mode="activeTab"
        @chat="onChat"
        @delete="onDelete"
        @add="onAdd"
        @cancel="onCancel"
        @accept="onAccept"
        @reject="onReject"
      />
    </div>
  </b-container>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useAuthStore } from '@/store/auth';
import FriendCard from '@/components/FriendCard.vue';

interface Friend {
  user_id: string;
  username: string;
  avatar?: string;
}

// Union всех табов
type Mode = 'friends' | 'add' | 'sent' | 'received';

const auth = useAuthStore();
const activeTab = ref<Mode>('friends');
const search = ref('');

const friends = ref<Friend[]>([]);
const searchResults = ref<Friend[]>([]);
const sentRequests = ref<Friend[]>([]);
const receivedRequests = ref<Friend[]>([]);

const tabs = [
  { label: 'Friends List',  value: 'friends'  as Mode },
  { label: 'Add New Friend', value: 'add'      as Mode },
  { label: 'Sent Request',   value: 'sent'     as Mode },
  { label: 'Received Request',  value: 'received' as Mode },
] as const;

const title = computed(() =>
  tabs.find(t => t.value === activeTab.value)!.label
);


// ——— Загрузчики ———
async function loadFriends() {
  const res = await fetch('http://127.0.0.1:8000/friends', {
    headers: { Authorization: auth.authHeader }
  });
  friends.value = res.ok ? await res.json() : [];
}

async function loadRequests() {
  const res = await fetch('http://127.0.0.1:8000/friends/requests', {
    headers: { Authorization: auth.authHeader }
  });
  if (!res.ok) return;

  const data = await res.json() as { incoming: string[]; outgoing: string[] };
  // подгружаем объекты пользователей по ID
  async function fetchUser(id: string): Promise<Friend> {
    const r = await fetch(`http://127.0.0.1:8000/users/${id}`, {
      headers: { Authorization: auth.authHeader }
    });
    return r.ok ? await r.json() : { user_id: id, username: 'Unknown' };
  }

  sentRequests.value     = await Promise.all(data.outgoing.map(fetchUser));
  receivedRequests.value = await Promise.all(data.incoming.map(fetchUser));
}

// при смене таба
watch(activeTab, () => {
  search.value = '';
  if (activeTab.value === 'friends') loadFriends();
  else if (activeTab.value === 'add') searchResults.value = [];
  else loadRequests();
}, { immediate: true });

function selectTab(tab: Mode) {
  activeTab.value = tab;
}

// ——— Поиск ———
async function onSearch() {
  if (activeTab.value === 'add') {
    const params = new URLSearchParams({ username: search.value });
    const res = await fetch(
      `http://127.0.0.1:8000/friends/search?${params}`,
      { headers: { Authorization: auth.authHeader } }
    );
    searchResults.value = res.ok ? await res.json() : [];
  }
  // иначе фильтрация на клиенте в computed
}

const displayList = computed<Friend[]>(() => {
  if (activeTab.value === 'friends') return filterBySearch(friends.value);
  if (activeTab.value === 'add')     return searchResults.value;
  if (activeTab.value === 'sent')    return sentRequests.value;
  return receivedRequests.value;
});
function filterBySearch(list: Friend[]) {
  if (!search.value.trim()) return list;
  const q = search.value.toLowerCase();
  return list.filter(f => f.username.toLowerCase().includes(q));
}

// ——— Действия ———
async function onChat(f: Friend) {
  // пока просто логи, позже с чатом
  console.log('Chat with', f);
}
async function onDelete(f: Friend) {
  await fetch(`http://127.0.0.1:8000/friends/${f.user_id}`, {
    method: 'DELETE',
    headers: { Authorization: auth.authHeader }
  });
  loadFriends();
}
async function onAdd(f: Friend) {
  await fetch('http://127.0.0.1:8000/friends/request', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: auth.authHeader
    },
    body: JSON.stringify({ target_user_id: f.user_id })
  });
  selectTab('sent');
}
async function onCancel(f: Friend) {
  await fetch(`http://127.0.0.1:8000/friends/requests/${f.user_id}`, {
    method: 'DELETE',
    headers: { Authorization: auth.authHeader }
  });
  loadRequests();
}
async function onAccept(f: Friend) {
  await fetch('http://127.0.0.1:8000/friends/accept', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: auth.authHeader
    },
    body: JSON.stringify({ requester_user_id: f.user_id })
  });
  loadRequests();
}
async function onReject(f: Friend) {
  await fetch('http://127.0.0.1:8000/friends/reject', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: auth.authHeader
    },
    body: JSON.stringify({ requester_user_id: f.user_id })
  });
  loadRequests();
}
</script>
