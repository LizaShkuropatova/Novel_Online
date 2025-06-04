import { defineStore } from 'pinia';
import type { INovelCharacter } from '~/types/character';

import { useAuthStore } from '~/store/auth';

export const useCharacterStore = defineStore('character-editor', {
 state: (): { character: INovelCharacter } => ({
  character: {
   character_id: '',
   novel_id: '',
   user_id: '',
   role: 'player',
   name: '',
   appearance: '',
   backstory: '',
   traits: '',
  },
 }),
 getters: {
  isCharacterLoaded: state => !!state.character.character_id,
 },
 actions: {
  setCharacter(data: INovelCharacter) {
   this.character = data;
  },

  updateField<K extends keyof INovelCharacter>(key: K, value: INovelCharacter[K]) {
   this.character[key] = value;
  },

  async fetchUserCharacter(novelId: string): Promise<void> {
   const auth = useAuthStore();

   const response = await fetch(`http://127.0.0.1:8000/novels/${novelId}/characters`, {
    method: 'GET',
    headers: {
     Authorization: `Bearer ${auth.accessToken}`,
     Accept: 'application/json',
    },
   });

   if (!response.ok) {
    throw new Error('Failed to load novel');
   }

   const responseData = await response.json();
   // find our character in the list of all characters
   const characterData = responseData.find((char: INovelCharacter) => char.user_id === auth.user?.user_id);
   if (characterData) {
    this.setCharacter(characterData);
   }
  },

  reset() {
   this.character = {
    character_id: '',
    novel_id: '',
    user_id: '',
    role: 'player',
    name: '',
    appearance: '',
    backstory: '',
    traits: '',
   };
  },
 },
});
