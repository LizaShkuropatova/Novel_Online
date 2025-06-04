import { defineStore } from 'pinia';
import type { IFirebaseNovel } from '~/types/novel';

export const useNovelStore = defineStore('novel', {
 state: (): { novel: IFirebaseNovel | null } => ({
  novel: null as IFirebaseNovel | null,
 }),

 actions: {
  setNovel(data: IFirebaseNovel) {
   this.novel = data;
  },

  updateField<K extends keyof IFirebaseNovel>(key: K, value: IFirebaseNovel[K]) {
   this.novel[key] = value;
  },

  reset() {
   this.novel = null;
  },
 },
});
