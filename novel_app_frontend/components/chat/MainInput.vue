<template>
 <div class="border-top py-2">
  <div class="d-flex">
   <BFormTextarea
    v-model="inputText"
    :placeholder="placeholder"
    rows="3"
    @update:model-value="handleInputChange"
    @keyup.enter="submit"
   />
  </div>
  <div class="d-flex justify-content-end mt-2 gap-2">
   <b-button
    color="teal-400"
    text-color="white"
    icon="bi:stars"
    @click="generateText"
   >
    Choises
   </b-button>
   <b-button
    color="teal-600"
    text-color="white"
    icon="bi:stars"
    @click="generateText"
   >
    Generate
   </b-button>
   <b-button
    color="primary"
    @click="submit"
   >
    Send
   </b-button>
  </div>
 </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';

const props = defineProps<{
 modelValue?: string;
 placeholder?: string;
}>();

const emit = defineEmits<{
 (e: 'submitted', value: string): void;
 (e: 'ai-generate'): void;
 (e: 'update:modelValue', value: string): void;
}>();

const inputText = ref<string>(props.modelValue || '');

watch(() => props.modelValue, (val) => {
 inputText.value = val || '';
});

const submit = (): void => {
 if (!inputText.value.trim()) return;
 emit('submitted', inputText.value);
};

const generateText = (): void => {
 emit('ai-generate');
};

function handleInputChange(value: string) {
 emit('update:modelValue', value);
}
</script>

<style scoped>
/* optional styles */
</style>
