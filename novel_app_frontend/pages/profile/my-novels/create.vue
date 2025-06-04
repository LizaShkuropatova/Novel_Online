<template>
 <div>
  <GenresSelect
   v-model="selectedGenres"
   @submit="handleGenresSubmit"
  />
 </div>
</template>

<script lang="ts" setup>
import { useAuthStore } from '@/store/auth';
import { useNovelStore } from '~/store/novel-editor';
import GenresSelect from '~/components/novel-editor/GenresSelect.vue';
import type { IFirebaseNovel } from '~/types/novel';

definePageMeta({
 middleware: 'auth',
});

const auth = useAuthStore();
const novelStore = useNovelStore();
const router = useRouter();

const selectedGenres = ref<string[]>([]);

function handleGenresSubmit() {
 submitGenres();
}

async function submitGenres() {
 try {
  const token = auth.accessToken;

  const { data, error } = await useFetch('http://127.0.0.1:8000/novels', {
   method: 'POST',
   headers: {
    Authorization: `Bearer ${token}`,
    Accept: 'application/json',
   },
   body: {
    genres: selectedGenres.value,
   },
  });

  if (error.value) {
   console.error('Error while creating new novel:', error.value);
   return;
  }

  console.log('Novel created:', data.value);

  novelStore.setNovel(data.value as IFirebaseNovel);
  // Navigation to the Next step
  router.push(`/profile/my-novels/${data.value.novel_id}/edit`);
 }
 catch (e) {
  console.error('Error while creating new novel', e);
 }
}
</script>
