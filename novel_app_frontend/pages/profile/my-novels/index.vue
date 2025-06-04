<template>
 <Container class="py-4">
  <!-- Шапка профиля -->
  <div>
   <div
    v-if="auth.user"
    class="d-flex flex-column align-items-center mb-4"
   >
    <img
     v-if="avatarUrl"
     :src="avatarUrl"
     alt="Avatar"
     class="rounded-circle mb-2"
     style="width: 80px; height: 80px;"
    >
    <h4 class="mb-2">
     {{ auth.user.username }}
    </h4>
    <Button
     class="btn btn-outline-secondary"
     size="sm"
     variant="outline-secondary"
     @click="$router.push('/settings')"
    >
     Profile settings
    </Button>
   </div>
  </div>

  <!-- существующий компонент со списком новел -->
  <MyList v-if="!loading && auth.user" />
 </Container>
</template>

<script setup lang="ts">
// Опционально, если нужно другой layout
// definePageMeta({ layout: 'default' })

import { ref, computed, onMounted } from 'vue';
import { useAuthStore } from '@/store/auth';
import { useRuntimeConfig } from '#app';
import MyList from '@/components/novels/MyList.vue';

definePageMeta({
 middleware: 'auth',
});

const auth = useAuthStore();
const config = useRuntimeConfig();

// Собираем полный URL аватарки (если в auth.user.avatar лежит относительная ссылка)
const avatarUrl = computed(() => {
 const a = auth.user?.avatar;
 if (!a) return '';
 // если уже абсолютный URL — возвращаем как есть
 if (a.startsWith('http')) return a;
 // иначе — склеиваем с базой
 return `${config.public.apiBase}${a}`;
});
</script>
