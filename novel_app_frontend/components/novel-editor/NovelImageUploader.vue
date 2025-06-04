<template>
 <div class="text-center">
  <div class="mb-3">
   <img
    :src="currentImageUrl"
    alt="Novel Cover"
    class="img-fluid rounded shadow-sm"
    style="max-height: 300px; object-fit: cover;"
   >
  </div>

  <input
   ref="fileInput"
   type="file"
   class="d-none"
   accept="image/*"
   @change="handleFileChange"
  >

  <button
   class="btn btn-outline-primary"
   @click="triggerFileInput"
  >
   Upload
  </button>
 </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { useCookie } from '#app';
import imgPlaceholder from '@/assets/img/image-placeholder.svg';

const props = defineProps<{
 novelId: string;
 imageUrl?: string;
}>();

const emit = defineEmits<{
 (e: 'update:imageUrl', url: string): void;
}>();

const fileInput = ref<HTMLInputElement | null>(null);
const uploadedUrl = ref<string | null>(null);

// const placeholder = '/assets/img/image-placeholder.svg'; // your fallback image path

// Prioritize uploaded URL over prop
const currentImageUrl = computed(() => uploadedUrl.value || props.imageUrl || imgPlaceholder);

function triggerFileInput(): void {
 fileInput.value?.click();
}

async function handleFileChange(event: Event): Promise<void> {
 const input = event.target as HTMLInputElement;
 const file = input.files?.[0];

 if (!file) return;

 const formData = new FormData();
 formData.append('file', file);

 const token = useCookie('access_token').value;

 try {
  const response = await fetch(`http://127.0.0.1:8000/novels/${props.novelId}/images`, {
   method: 'POST',
   headers: {
    Authorization: `Bearer ${token}`,
    Accept: 'application/json',
   },
   body: formData,
  });

  if (!response.ok) {
   throw new Error(`Upload failed with status ${response.status}`);
  }

  const result = await response.json();
  const newUrl = result.cover_image_url;

  uploadedUrl.value = newUrl;
  emit('update:imageUrl', newUrl);
 }
 catch (error) {
  console.error('Image upload error:', error);
  alert('Failed to upload image.');
 }
 finally {
  input.value = ''; // reset for next selection
 }
}
</script>
