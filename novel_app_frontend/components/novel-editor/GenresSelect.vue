<template>
 <div>
  <label class="form-label fw-bold">Select genres</label>

  <div
   v-if="genres.length === 0"
   class="text-muted small"
  >
   Loading...
  </div>

  <div
   v-else
   class="d-flex flex-wrap gap-2"
  >
   <div
    v-for="genre in genres"
    :key="genre"
    class="form-check"
   >
    <input
     :id="genre"
     v-model="internalValue"
     class="form-check-input"
     type="checkbox"
     :value="genre"
    >
    <label
     class="form-check-label text-capitalize"
     :for="genre"
    >
     {{ genre.replaceAll('_', ' ') }}
    </label>
   </div>
  </div>

  <div
   v-if="genres.length !== 0"
   class="mt-4 d-flex"
  >
   <button
    class="btn btn-primary"
    :disabled="props.modelValue.length < 1"
    @click="handleButtonClick"
   >
    Next
   </button>
  </div>
 </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';

const props = defineProps<{
 modelValue: string[];
}>();

const emit = defineEmits<{
 (e: 'update:modelValue', value: string[]): void;
 (e: 'submit'): void;
}>();

const genres = ref<string[]>([]);
const internalValue = ref<string[]>([...props.modelValue]);

watch(internalValue, (val) => {
 emit('update:modelValue', val);
});

function handleButtonClick() {
 emit('submit');
}

onMounted(async () => {
 try {
  const res = await fetch('http://127.0.0.1:8000/novels/genres');
  genres.value = await res.json();
 }
 catch (err) {
  console.error('Error loading genres:', err);
 }
});
</script>
