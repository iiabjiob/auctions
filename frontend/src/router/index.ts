import { createRouter, createWebHistory } from 'vue-router'
import { defineComponent } from 'vue'
import AnalysisConfigRoute from '@/views/AnalysisConfigRoute.vue'
import InterestProfilesRoute from '@/views/InterestProfilesRoute.vue'

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
    {
      path: '/analysis-config',
      name: 'analysis-config',
      component: AnalysisConfigRoute,
    },
    {
      path: '/interest-profiles',
      name: 'interest-profiles',
      component: InterestProfilesRoute,
    },
  ],
})

export default router
