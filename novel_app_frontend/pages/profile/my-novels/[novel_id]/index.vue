<template>
 <div class="container py-4">
  <div
   v-if="!novel"
   class="text-muted text-center"
  >
   Loading...
  </div>
  <template v-else>
   <NovelGeneralInfo :novel="novel" />
   <NuxtLink
    :to="`/profile/my-novels/${novel.novel_id}/edit`"
    class="btn btn-outline-secondary d-flex align-items-center gap-2 my-1"
   >
    <BIcon
     icon="bi:pencil-square"
    />
    Edit
   </NuxtLink>
   <NuxtLink
    :to="`/novels/${novelId}/play`"
    class="btn btn-primary d-flex align-items-center gap-2 my-1"
   >
    <BIcon
     icon="bi:play-circle"
    />
    Play
   </NuxtLink>
  </template>
 </div>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router';
import { useNovelStore } from '~/store/novel-editor';
import NovelGeneralInfo from '~/components/novels/NovelGeneralInfo.vue';

const route = useRoute();
const novelId = route.params.novel_id as string;

const novelStore = useNovelStore();

// Fetch and store novel in Pinia
await useAsyncData(`novel-${novelId}`, async () => {
 const response = await fetch(`http://127.0.0.1:8000/novels/${novelId}`, {
  headers: {
   Accept: 'application/json',
  },
 });

 if (!response.ok) {
  throw createError({
   statusCode: response.status,
   message: 'Failed to load novel',
  });
 }

 const data = await response.json();
 novelStore.setNovel(data);
 return data;
});

// Local ref to store novel for rendering
const novel = computed(() => novelStore.novel);
</script>
