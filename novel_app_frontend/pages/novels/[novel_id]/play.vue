<template>
 <b-container class="d-flex flex-column chat-wrapper">
  <div
   ref="chatContainer"
   class="flex-grow-1 overflow-auto pt-3"
  >
   <!--   <pre>{{ segments }}</pre> -->
   <ChatMessage
    v-for="segment in segments"
    :key="segment.segment_id"
    :segment="segment"
    :novel-id="novelId"
    @updated="handleSegmentUpdate"
    @deleted="handleSegmentDelete"
   />
  </div>
  <ChatMainInput
   v-model="mainInputValue"
   placeholder="Write your story"
   @submitted="handleSubmit"
   @ai-generate="handleGenerated"
  />
 </b-container>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router';
import type { ITextSegment } from '~/types/TextSegment';

const hasPrologue = computed(() => segments.value.length > 0);

const route = useRoute();
const novelId = route.params.novel_id as string;
const segments = ref([]);

const mainInputValue = ref('');

const fetchSegments = async () => {
 const res = await fetch(`http://127.0.0.1:8000/novels/${novelId}/text/segments`);
 if (res.ok) {
  segments.value = await res.json();
 }
 else {
  console.error('Failed to load segments');
 }
};

onMounted(() => {
 fetchSegments();
});

async function handleSubmit(newText: string) {
 const token = useCookie('access_token').value;

 try {
  const response = await fetch(`http://127.0.0.1:8000/novels/${novelId}/text/segments`, {
   method: 'POST',
   headers: {
    'Authorization': `Bearer ${token}`,
    'Accept': 'application/json',
    'Content-Type': 'application/json',
   },
   body: JSON.stringify({
    content: newText,
   }),
  });

  if (!response.ok) {
   const errorText = await response.text();
   throw new Error(`Server responded with ${response.status}: ${errorText}`);
  }
  else {
   const newSegment = await response.json();
   segments.value.push(newSegment);
   mainInputValue.value = '';
  }
 }
 catch (err) {
  console.error('Failed to POST text segment:', err);
 }
};

const handleGenerated = () => {
 // optional: insert into input
 console.log('on generated');
 if (hasPrologue.value) {
  aiGenerateNextTextSegment();
 }
 else {
  aiGeneratePrologue();
 }
};

const handleSegmentUpdate = (updatedSegment: ITextSegment) => {
 segments.value = segments.value.map((segment: ITextSegment) => {
  if (segment.segment_id === updatedSegment.segment_id) {
   return updatedSegment;
  }
  return segment;
 });
};

const handleSegmentDelete = (id: string) => {
 segments.value = segments.value.filter((segment: ITextSegment) => segment.segment_id !== id);
};

async function aiGeneratePrologue() {
 console.log('aiGeneratePrologue');
 const token = useCookie('access_token').value;

 try {
  const response = await fetch(`http://127.0.0.1:8000/ai/novels/${novelId}/text/prologue`, {
   method: 'POST',
   headers: {
    Authorization: `Bearer ${token}`,
    Accept: 'application/json',
   },
  });

  if (!response.ok) {
   const errorText = await response.text();
   throw new Error(`Server responded with ${response.status}: ${errorText}`);
  }
  else {
   const newSegment = await response.json();
   mainInputValue.value = newSegment.content;
  }
 }
 catch (err) {
  console.error('Failed to generate prologue:', err);
 }
}

async function aiGenerateNextTextSegment() {
 console.log('aiGenerateNextTextSegment');
 const token = useCookie('access_token').value;

 try {
  const response = await fetch(`http://127.0.0.1:8000/ai/novels/${novelId}/text/continue`, {
   method: 'POST',
   headers: {
    Authorization: `Bearer ${token}`,
    Accept: 'application/json',
   },
  });

  if (!response.ok) {
   const errorText = await response.text();
   throw new Error(`Server responded with ${response.status}: ${errorText}`);
  }
  else {
   const newSegment = await response.json();
   mainInputValue.value = newSegment.content;
  }
 }
 catch (err) {
  console.error('Failed to next text segment:', err);
 }
}
</script>

<style scoped>
.chat-wrapper {
  height: calc(100vh - 50px);
}
#chatContainer::-webkit-scrollbar {
  display: none;
}
</style>
