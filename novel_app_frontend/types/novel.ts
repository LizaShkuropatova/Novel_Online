export interface IFirebaseNovel {
 novel_id: string;
 novel_original_id: string;
 users_author: string[];
 user_players: string[];
 title: string;
 description: string;
 genres: string[]; // or: Genre[] if you have an enum
 setting: string;
 created_at: string; // ISO date string
 updated_at: string;
 is_public: boolean;
 cover_image_url: string;
 state: 'planned' | 'active' | 'finished'; // or: NovelState if it's enum
 current_position: string;
 ended_at: string;
}
