<template>
 <div>
  <!-- Кнопка открытия -->
  <b-button
   color="primary"
   @click="openModal"
  >
   Filter Genres
  </b-button>

  <!-- Модальное окно -->
  <Modal
   ref="demoModal"
  >
   <ModalDialog>
    <ModalContent>
     <ModalHeader>
      <ModalTitle>Choose genres</ModalTitle>
      <CloseButton dismiss="modal" />
     </ModalHeader>

     <ModalBody>
      <div
       v-if="genres.length === 0"
       class="text-muted"
      >
       Loading genres...
      </div>
      <div
       v-else
       class="d-flex flex-column gap-2"
      >
       <div
        v-for="genre in genres"
        :key="genre"
        class="form-check"
       >
        <input
         :id="genre"
         v-model="localSelectedGenres"
         class="form-check-input"
         type="checkbox"
         :value="genre"
        >
        <label
         class="form-check-label"
         :for="genre"
        >
         {{ genre }}
        </label>
       </div>
      </div>
     </ModalBody>

     <ModalFooter>
      <!-- Reset button -->
      <b-button
       color="warning"
       @click="resetSelection"
      >
       Reset
      </b-button>
      <b-button
       color="secondary"
       @click="closeModal"
      >
       Cancel
      </b-button>
      <b-button
       color="primary"
       @click="applyAndClose"
      >
       Apply Filter
      </b-button>
     </ModalFooter>
    </ModalContent>
   </ModalDialog>
  </Modal>
 </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';

// ссылки на пропсы и эмиты
const props = defineProps<{ modelValue: string[] }>();
const emit = defineEmits<{
 (e: 'update:modelValue', val: string[]): void;
}>();

// локальное состояние
const genres = ref<string[]>([]);
const localSelectedGenres = ref<string[]>([...props.modelValue]);

// реф на модалку
const demoModal = ref<InstanceType<typeof import('bootstrap-vue-3').Modal> | null>(null);

// синхронизируем внешнее и локальное selected
watch(
 () => props.modelValue,
 (val) => {
  localSelectedGenres.value = [...val];
 },
);

// загрузка списка жанров
onMounted(async () => {
 try {
  const res = await fetch('http://127.0.0.1:8000/novels/genres');
  if (!res.ok) throw new Error('Failed to fetch genres');
  genres.value = await res.json();
 }
 catch (e) {
  console.error(e);
 }
});

// открытие/закрытие модалки
const openModal = () => {
 demoModal.value?.show();
};
const closeModal = () => {
 demoModal.value?.hide();
};

// сброс выбора жанров без эмита
const resetSelection = () => {
 localSelectedGenres.value = [];
};

// по клику “Apply Filter” — эмитим и закрываем
const applyAndClose = () => {
 emit('update:modelValue', localSelectedGenres.value);
 closeModal();
};
</script>
