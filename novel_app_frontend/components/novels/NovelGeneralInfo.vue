<template>
 <div class="row g-4">
  <div class="col-md-4 text-center">
   <img
    :src="novel.cover_image_url || '/assets/img/image-placeholder.svg'"
    alt="Cover"
    class="img-fluid rounded shadow-sm"
    style="max-height: 400px; object-fit: cover; width: 100%;"
   >
  </div>

  <div class="col-md-8">
   <h1 class="mb-3">
    {{ novel.title }}
   </h1>

   <div class="mb-4">
    <h5 class="text-secondary">
     Description
    </h5>
    <p>{{ novel.description || 'No description provided.' }}</p>
   </div>

   <div>
    <h5 class="text-secondary">
     Setting
    </h5>
    <p>{{ novel.setting || 'No setting provided.' }}</p>
   </div>
  </div>
 </div>
</template>

<script setup lang="ts">
import type { IFirebaseNovel } from '~/types/novel';

defineProps<{
 novel: IFirebaseNovel;
}>();
</script>
