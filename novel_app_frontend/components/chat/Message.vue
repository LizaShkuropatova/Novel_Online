<template>
 <div
  v-if="!isEditing"
  class="mb-3"
 >
  <b-card
   class="p-2 mb-1"
   color="teal-100"
  >
   <p class="mb-2">
    {{ segment.content }}
   </p>
  </b-card>
  <div class="d-flex justify-content-end">
   <b-button
    size="sm"
    icon="bi:trash"
    @click="handleDelete"
   >
    Delete
   </b-button>
   <b-button
    size="sm"
    class="me-2"
    icon="bi:pencil"
    @click="startEdit"
   >
    Edit
   </b-button>
  </div>
 </div>
 <div v-else>
  <b-card
   class="p-2 mb-1"
   color="teal-100"
  >
   <b-form-textarea
    v-model="editedText"
    rows="5"
    class="mb-2"
   />
   <div class="d-flex justify-content-end">
    <b-button
     size="sm"
     icon="bi:x"
     variant="secondary"
     @click="cancelEdit"
    >
     Cancel
    </b-button>
    <b-button
     class="me-2"
     size="sm"
     color="success"
     icon="bi:check"
     @click="saveEdit"
    >
     Save
    </b-button>
   </div>
  </b-card>
 </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import type { ITextSegment } from '~/types/TextSegment';

const props = defineProps<{
 segment: ITextSegment;
 novelId: string;
}>();

const emit = defineEmits<{
 (e: 'updated', segment: ITextSegment): void;
 (e: 'deleted', segmentId: string): void;
}>();

const isEditing = ref<boolean>(false);
const editedText = ref<string>(props.segment.content);

const startEdit = (): void => {
 isEditing.value = true;
 editedText.value = props.segment.content;
};

const cancelEdit = (): void => {
 isEditing.value = false;
};

const saveEdit = async (): Promise<void> => {
 const token = useCookie('access_token').value;

 try {
  const response = await fetch(`http://127.0.0.1:8000/novels/${props.novelId}/text/segments/${props.segment.segment_id}`, {
   method: 'PUT',
   headers: {
    'Authorization': `Bearer ${token}`,
    'Accept': 'application/json',
    'Content-Type': 'application/json',
   },
   body: JSON.stringify({ content: editedText.value }),
  });
  if (response.ok) {
   isEditing.value = false;
   emit('updated', { ...props.segment, content: editedText.value });
  }
  else {
   throw new Error('Failed to update segment');
  }
 }
 catch (error) {
  console.error('Failed to update segment: ', error);
 }
};

const handleDelete = async (): Promise<void> => {
 const token = useCookie('access_token').value;

 try {
  const res = await fetch(`http://127.0.0.1:8000/novels/${props.novelId}/text/segments/${props.segment.segment_id}`, {
   method: 'DELETE',
   headers: {
    Authorization: `Bearer ${token}`,
    Accept: 'application/json',
   },
  });
  if (res.ok) {
   emit('deleted', props.segment.segment_id);
  }
  else {
   throw new Error('Failed to delete segment');
  }
 }
 catch (error) {
  console.error('Failed to delete segment: ', error);
 }
};
</script>

<style scoped>
/* optional styles */
</style>
