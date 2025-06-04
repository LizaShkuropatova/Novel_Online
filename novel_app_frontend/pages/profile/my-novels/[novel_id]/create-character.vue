<template>
 <div class="container py-4">
  <h1>Character creation</h1>

  <character-form />

  <div class="d-flex justify-content-center mt-4">
   <NuxtLink
    :to="`/profile/my-novels/${novelId}`"
    class="btn btn-outline-secondary d-flex align-items-center gap-2 mx-1"
   >
    <BIcon
     icon="bi:chevron-left"
    />
    Back
   </NuxtLink>
   <button
    class="btn btn-success mx-1"
    :disabled="isSubmitting"
    @click="onSubmitCreateCharacter"
   >
    <span
     v-if="isSubmitting"
     class="spinner-border spinner-border-sm me-2"
    />
    {{ isSubmitting ? 'Saving...' : 'Create character' }}
   </button>
  </div>
 </div>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router';
import CharacterForm from '~/components/novel-editor/CharacterForm.vue';
import { useCharacterStore } from '~/store/character';

definePageMeta({
 middleware: 'auth',
});

const isSubmitting = ref(false);
const route = useRoute();
const novelId = computed(() => route.params.novel_id as string);
const characterStore = useCharacterStore();

async function onSubmitCreateCharacter() {
 isSubmitting.value = true;
 const token = useCookie('access_token').value;

 try {
  const response = await fetch(`http://127.0.0.1:8000/novels/${novelId.value}/characters`, {
   method: 'POST',
   headers: {
    'Authorization': `Bearer ${token}`,
    'Accept': 'application/json',
    'Content-Type': 'application/json',
   },
   body: JSON.stringify(characterStore.character),
  });

  if (!response.ok) {
   const errorText = await response.text();
   throw new Error(`Server responded with ${response.status}: ${errorText}`);
  }

  const result = await response.json();
  alert('Character saved successfully.');
  navigateTo(`/profile/my-novels/${novelId.value}/characters/${result.character_id}`);
 }
 catch (err) {
  console.error('Failed to save Character:', err);
  alert('Failed to save Character.');
 }
 finally {
  isSubmitting.value = false;
 }
}
</script>
