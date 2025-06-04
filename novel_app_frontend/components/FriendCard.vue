<template>
  <div class="d-flex align-items-center p-2 border-bottom">
    <!-- Вместо <Avatar> теперь обычный <img> -->
    <img
      :src="avatarUrl || defaultAvatar"
      alt="Avatar"
      class="rounded-circle me-3"
      style="width: 40px; height: 40px; object-fit: cover;"
    />

    <div class="flex-grow-1">
      <h5 class="mb-0">{{ friend.username }}</h5>
    </div>

    <div class="d-flex gap-2">
      <b-button
        v-if="mode === 'friends'"
        size="sm"
        variant="outline-secondary"
        @click="$emit('chat', friend)"
      >
        Chat
      </b-button>
      <b-button
        v-if="mode === 'friends'"
        size="sm"
        variant="outline-danger"
        @click="$emit('delete', friend)"
      >
        Delete
      </b-button>
      <b-button
        v-if="mode === 'add'"
        size="sm"
        variant="outline-success"
        @click="$emit('add', friend)"
      >
        Add
      </b-button>
      <b-button
        v-if="mode === 'sent'"
        size="sm"
        variant="outline-warning"
        @click="$emit('cancel', friend)"
      >
        Cancel
      </b-button>
      <b-button
        v-if="mode === 'received'"
        size="sm"
        variant="outline-primary"
        @click="$emit('accept', friend)"
      >
        Accept
      </b-button>
      <b-button
        v-if="mode === 'received'"
        size="sm"
        variant="outline-danger"
        @click="$emit('reject', friend)"
      >
        Reject
      </b-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRuntimeConfig } from '#app';

interface Friend {
  user_id: string;
  username: string;
  avatar?: string; // относительный путь или полный URL
}

const props = defineProps<{
  friend: Friend;
  mode: 'friends' | 'add' | 'sent' | 'received';
}>();

// плейсхолдер, если у пользователя нет аватарки:
const defaultAvatar = '/images/default-avatar.png'; // создайте этот файл в public/images/

// соберём полный URL аватарки:
const config = useRuntimeConfig();
const avatarUrl = computed(() => {
  const a = props.friend.avatar;
  if (!a) return '';
  // если строка уже абсолютная
  if (a.startsWith('http://') || a.startsWith('https://')) {
    return a;
  }
  // иначе — добавляем базу
  return `${config.public.apiBase}${a}`;
});

// эмитим события дальше
defineEmits<{
  (e: 'chat', friend: Friend): void;
  (e: 'delete', friend: Friend): void;
  (e: 'add', friend: Friend): void;
  (e: 'cancel', friend: Friend): void;
  (e: 'accept', friend: Friend): void;
  (e: 'reject', friend: Friend): void;
}>();
</script>
