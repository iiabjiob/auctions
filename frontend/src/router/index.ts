import { createRouter, createWebHistory } from 'vue-router'
import { defineComponent } from 'vue'

const EmptyRouteView = defineComponent({
  name: 'EmptyRouteView',
  setup: () => () => null,
})

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/auctions',
    },
    {
      path: '/auctions',
      name: 'auctions',
      component: EmptyRouteView,
    },
    {
      path: '/tenders',
      name: 'tenders',
      component: EmptyRouteView,
    },
    {
      path: '/help',
      name: 'help',
      component: EmptyRouteView,
    },
    {
      path: '/diagnostics',
      name: 'diagnostics',
      component: EmptyRouteView,
    },
  ],
})

export default router
