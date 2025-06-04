<template>
 <PageLayout type="three-columns">
  <template #header>
   <ShareHeaderDocs />
  </template>
  <template #start>
   <Sidebar
    id="sidebar"
    active-background-color="teal-700"
    :data="computedSidebarRoutes"
   />
  </template>
  <template #end>
   <Toc
    selector="#content"
    display="none lg-block print-none"
    color="teal-700"
   >
    <Localization>
     <template #en>
      On this page
     </template>
     <template #ja>
      項目
     </template>
    </Localization>
   </Toc>
  </template>
  <template #default>
   <b-div
    id="content"
   >
    <slot />
   </b-div>
  </template>
  <!--  <template #footer> -->
  <!--   <ShareFooter /> -->
  <!--  </template> -->
 </PageLayout>
</template>

<script lang="ts" setup>
import { useAuthStore } from '@/store/auth';

const auth = useAuthStore();
const router = useRouter();

const defaultSidebarRoutes = [
 {
  name: 'Online Novels',
  icon: 'bi:book-half',
  color: 'indigo',
  children: [
   {
    name: 'Home page',
    path: '/',
   },
  ],
 },
];

const loggedInSidebarRoutes = [
 {
  name: 'Profile',
  icon: 'bi:person-circle',
  color: 'indigo',
  children: [
   {
    name: 'My Novels',
    path: '/profile/my-novels',
   },
   {
    name: 'Create new novel',
    path: '/profile/my-novels/create',
   },
   {
    name: 'Friends list',
    path: '/profile/friends',
   },
   {
    name: 'Messages',
    path: '/profile/messages',
   },
   {
    name: 'Notifications',
    path: '/profile/notification',
   },
   {
    name: 'Logout',
    path: '/logout',
   },
  ],
 },
];

const anonymousSidebarRoutes = [
 {
  name: 'Authorization',
  icon: 'bi:person-circle',
  color: 'indigo',
  children: [
   {
    name: 'Sign-in',
    path: '/sign-in',
   },
   {
    name: 'Sign-up',
    path: '/sign-up',
   },
  ],
 },
];

const isLoggedIn = computed(() => auth.isAuthenticated);

const computedSidebarRoutes = computed(() => {
 if (isLoggedIn.value) {
  return [...defaultSidebarRoutes, ...loggedInSidebarRoutes];
 }
 else {
  return [...defaultSidebarRoutes, ...anonymousSidebarRoutes];
 }
});
</script>
