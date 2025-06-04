<template>
 <div>
  <AiAssistedInput
   v-model="name"
   label="Name"
   name="name"
   :loading="isLoadingName"
   @generate="generateMetadataFieldWithAi('name')"
  />
  <AiAssistedInput
   v-model="appearance"
   label="Appearance"
   name="appearance"
   :loading="isLoadingAppearance"
   @generate="generateMetadataFieldWithAi('appearance')"
  />
  <AiAssistedInput
   v-model="backstory"
   label="Backstory"
   name="backstory"
   :loading="isLoadingBackstory"
   @generate="generateMetadataFieldWithAi('backstory')"
  />
  <AiAssistedInput
   v-model="traits"
   label="Traits"
   name="traits"
   :loading="isLoadingTraits"
   @generate="generateMetadataFieldWithAi('traits')"
  />
 </div>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router';
import { useCharacterStore } from '~/store/character';

interface ICharacterFormProps {
}

defineProps<ICharacterFormProps>();

const characterStore = useCharacterStore();

const name = computed({
 get: () => characterStore.character?.name ?? '',
 set: (value: string) => {
  characterStore.updateField('name', value);
 },
});
const isLoadingName = ref(false);

const appearance = computed({
 get: () => characterStore.character?.appearance ?? '',
 set: (value: string) => {
  characterStore.updateField('appearance', value);
 },
});
const isLoadingAppearance = ref(false);

const backstory = computed({
 get: () => characterStore.character?.backstory ?? '',
 set: (value: string) => {
  characterStore.updateField('backstory', value);
 },
});
const isLoadingBackstory = ref(false);

const traits = computed({
 get: () => characterStore.character?.traits ?? '',
 set: (value: string) => {
  characterStore.updateField('traits', value);
 },
});
const isLoadingTraits = ref(false);

const route = useRoute();
const novelId = computed(() => route.params.novel_id as string);

async function generateMetadataFieldWithAi(fieldName: 'name' | 'appearance' | 'backstory' | 'traits'): Promise<void> {
 if (!novelId.value) {
  console.error('novel_id is missing');
  return;
 }

 const token = useCookie('access_token').value;

 const loadingMap = {
  name: isLoadingName,
  appearance: isLoadingAppearance,
  backstory: isLoadingBackstory,
  traits: isLoadingTraits,
 };

 const fieldLoading = loadingMap[fieldName];
 fieldLoading.value = true;

 try {
  const response = await fetch(`http://127.0.0.1:8000/ai/novels/${novelId.value}/character/generate`, {
   method: 'POST',
   headers: {
    'Authorization': `Bearer ${token}`,
    'Accept': 'application/json',
    'Content-Type': 'application/json',
   },
   body: JSON.stringify({
    role: 'player',
    fields: [fieldName],
    name: name.value,
    appearance: appearance.value,
    backstory: backstory.value,
    traits: traits.value,
   }),
  });

  if (!response.ok) {
   throw new Error(`AI generation failed: ${response.status} ${response.statusText}`);
  }

  const result = await response.json();
  const generatedValue = result[fieldName];

  if (generatedValue) {
   if (fieldName === 'name') {
    name.value = generatedValue;
   }
   else if (fieldName === 'appearance') {
    appearance.value = generatedValue;
   }
   else if (fieldName === 'backstory') {
    backstory.value = generatedValue;
   }
   else if (fieldName === 'traits') {
    traits.value = generatedValue;
   }
  }
  else {
   console.warn(`Field "${fieldName}" not found in AI response`);
  }
 }
 catch (err) {
  console.error('Error during AI-assisted metadata generation:', err);
  alert('Failed to generate content. Please try again.');
 }
 finally {
  fieldLoading.value = false;
 }
}
</script>

<style scoped lang="scss">
</style>
