<template>
 <PageLayout type="three-columns">
  <!-- HEADER -->
  <template #header>
   <div class="d-flex flex-column align-items-center py-4 border-bottom">
    <Avatar
     :src="auth.user?.avatar || ''"
     size="xl"
     rounded
     class="mb-3"
    />
    <h4 class="mb-2">
     {{ auth.user?.username }}
    </h4>
    <Button
     size="sm"
     variant="outline-secondary"
     @click="$router.push('/settings')"
    >
     Налаштування профілю
    </Button>
   </div>
  </template>

  <!-- SIDEBAR -->
  <template #start>
   <Sidebar
    id="sidebar"
    active-background-color="teal-700"
    :data="computedSidebarRoutes"
   />
  </template>

  <!-- DEFAULT SLOT -->
  <template #default>
   <b-div
    id="content"
    class="p-4"
   >
    <slot />
    <MyList />
   </b-div>
  </template>
 </PageLayout>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useAuthStore } from '@/store/auth';
import MyList from '@/components/novels/MyList.vue';

// НЕ ИМПОРТИРУЕМ '@/components/share/sidebar.vue' — Nuxt сам подхватит components/sidebar.vue
// ЕСЛИ ВАШ Sidebar ЛЕЖИТ В ДРУГОМ МЕСТЕ — ПРОПИШИТЕ ПРАВИЛЬНЫЙ ПУТЬ, например:
// import Sidebar from '@/components/sidebar.vue'

interface SidebarChild {
 name: string;
 path: string;
}
interface SidebarRoute {
 name: string;
 icon: string;
 color: string;
 children: SidebarChild[];
}

const defaultSidebarRoutes: SidebarRoute[] = [
 {
  name: 'Online Novels',
  icon: 'bi:book-half',
  color: 'indigo',
  children: [
   { name: 'Home page', path: '/' },
  ],
 },
];

const loggedInSidebarRoutes: SidebarRoute[] = [
 {
  name: 'Profile',
  icon: 'bi:person-circle',
  color: 'indigo',
  children: [
   { name: 'My Novels', path: '/mylist' },
   { name: 'Logout', path: '/logout' },
  ],
 },
];

const anonymousSidebarRoutes: SidebarRoute[] = [
 {
  name: 'Authorization',
  icon: 'bi:person-circle',
  color: 'indigo',
  children: [
   { name: 'Sign-in', path: '/sign-in' },
   { name: 'Sign-up', path: '/sign-up' },
  ],
 },
];

const auth = useAuthStore();
const isLoggedIn = computed(() => auth.isAuthenticated);
const computedSidebarRoutes = computed(() =>
 isLoggedIn.value
  ? [...defaultSidebarRoutes, ...loggedInSidebarRoutes]
  : [...defaultSidebarRoutes, ...anonymousSidebarRoutes],
);
</script>
