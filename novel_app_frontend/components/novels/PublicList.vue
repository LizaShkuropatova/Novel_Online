<template>
 <Container>
  <Row align-items="start">
   <!-- Search + Filter -->
   <div class="d-flex gap-2 mb-4 align-items-start">
    <!-- Поиск -->
    <div class="input-group input-group-sm flex-grow-1">
     <input
      v-model="search"
      type="text"
      class="form-control form-control-sm"
      placeholder="Search novels…"
     >
     <button
      class="btn btn-outline-primary btn-sm"
      @click="onSearchClick"
     >
      <i class="bi-search me-1" /> Search
     </button>
    </div>

    <!-- Кнопка фильтра -->
    <div class="filter-wrapper">
     <GenreFilterModal v-model="selectedGenres" />
    </div>
   </div>
  </Row>

  <!-- Сетка карточек -->
  <Row>
   <Col
    v-for="novel in filteredNovels"
    :key="novel.novel_id"
    col="4"
    class="mb-4"
   >
    <PublicListCard
     :novel="novel"
     :novel-url="`/novels/${novel.novel_id}`"
    />
   </Col>
   <Col
    v-if="filteredNovels.length === 0"
    col="12"
   >
    <p class="text-center text-muted">
     Nothing found
    </p>
   </Col>
  </Row>
 </Container>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import GenreFilterModal from './GenreFilterModal.vue';
import PublicListCard from './PublicListCard.vue';

interface Novel { novel_id: string; title: string; genres?: string[]; genre?: string }

const search = ref('');
const selectedGenres = ref<string[]>([]);
const novels = ref<Novel[]>([]);

async function fetchNovels() {
 try {
  let endpoint: string;
  if (selectedGenres.value.length > 0) {
   const url = new URL('http://127.0.0.1:8000/novels/public/by-all-genres');
   selectedGenres.value.forEach(g => url.searchParams.append('genres', g));
   endpoint = url.toString();
  }
  else {
   endpoint = 'http://127.0.0.1:8000/novels/public';
  }

  console.log('Fetching from', endpoint);
  const res = await fetch(endpoint);
  if (!res.ok) throw new Error(`Fetch ${res.status}`);
  novels.value = await res.json();
 }
 catch (e) {
  console.error(e);
  novels.value = [];
 }
}

watch(selectedGenres, () => {
 search.value = '';
 fetchNovels();
}, { immediate: true });

function onSearchClick() {
 /* поиск применяется в computed */
}

const filteredNovels = computed(() => {
 let list = novels.value;
 if (search.value.trim()) {
  const q = search.value.toLowerCase();
  list = list.filter(n => n.title.toLowerCase().includes(q));
 }
 return list;
});

onMounted(fetchNovels);
</script>

<style scoped>
/* Уменьшаем высоту Filter Genres кнопки внутри GenreFilterModal */
.filter-wrapper ::v-deep button.btn {
  padding: 0.25rem 0.5rem !important;
  font-size: 0.875rem !important;
  line-height: 1.2 !important;
}
</style>
