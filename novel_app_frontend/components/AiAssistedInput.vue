<template>
 <div class="mb-3">
  <label
   :for="name"
   class="form-label"
  >{{ label }}</label>
  <div class="input-group">
   <textarea
    :id="name"
    :name="name"
    class="form-control"
    rows="4"
    :value="modelValue"
    @input="$emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
   />
  </div>
  <button
   class="btn btn-outline-secondary d-flex align-items-center gap-1 my-2"
   type="button"
   :disabled="loading"
   @click="$emit('generate')"
  >
   <BIcon
    v-if="!loading"
    icon="bi:stars"
   />
   <span
    v-if="loading"
    class="spinner-border spinner-border-sm"
    role="status"
    aria-hidden="true"
   />
   <span>{{ loading ? 'Generating...' : 'Generate' }}</span>
  </button>
  <div
   v-if="hint"
   class="form-text mt-1 text-primary"
  >
   <BIcon
    icon="bi:info-circle"
   />
   {{ hint }}
  </div>
 </div>
</template>

<script setup lang="ts">
defineProps<{
 label: string;
 name: string;
 modelValue: string;
 loading?: boolean;
 hint?: string;
}>();

defineEmits<{
 (e: 'update:modelValue', value: string): void;
 (e: 'generate'): void;
}>();
</script>
