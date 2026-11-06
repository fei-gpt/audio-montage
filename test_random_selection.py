import unittest
from workbench.duration_planner import plan_by_duration


class RandomSelectionTest(unittest.TestCase):
    def candidates(self):
        return [dict(id=f'{i:03}',name=f'{i:03}.mp4',asset_sha256=f'source-{i}',start=0,end=1,frames=30,safe_trim_ranges=[]) for i in range(1,6)]

    def test_all_files_can_be_first_and_order_is_reproducible_per_seed(self):
        candidates=self.candidates()+[dict(id='030',name='030.mp4',asset_sha256='source-30',start=0,end=1,frames=30)]
        timeline={'segments':[{'end':1},{'end':2},{'end':3}]}
        orders=[]
        for seed in range(60):
            a=plan_by_duration(candidates,timeline,3,seed=seed)
            self.assertEqual(a,plan_by_duration(candidates,timeline,3,seed=seed))
            ids=tuple(p['shot_id'] for p in a['parts']);orders.append(ids)
            self.assertEqual(len(set(ids)),3)
            self.assertFalse(any(int(b)==int(a)+1 for a,b in zip(ids,ids[1:])))
            self.assertEqual(sum(p['frames'] for p in a['parts']),90)
        self.assertEqual({x[0] for x in orders},{c['id'] for c in candidates})
        self.assertGreater(len(set(orders)),10)
        self.assertNotEqual(orders,[('001','002','003')]*60)

    def test_shuffled_neighboring_numbers_are_still_clustered(self):
        from workbench.duration_planner import compact_number_run
        self.assertTrue(compact_number_run(['视频030.mp4','视频034.mp4','视频031.mp4']))
        self.assertFalse(compact_number_run(['视频030.mp4','视频005.mp4','视频050.mp4']))
        with self.assertRaises(ValueError):
            plan_by_duration(self.candidates(),{'segments':[{'end':3}]},3,seed=1)

    def test_random_search_still_avoids_used_ranges_and_rejected_sequences(self):
        candidates=self.candidates();timeline={'segments':[{'end':1}]}
        used=[dict(asset_sha256='source-1',start=0,end=1)]
        plan=plan_by_duration(candidates,timeline,1,used,seed=4,accept=lambda parts:parts[0]['shot_id']=='005')
        self.assertEqual(plan['parts'][0]['shot_id'],'005')

    def test_random_does_not_always_prefer_longest_clip(self):
        candidates=self.candidates()+[dict(id='long',asset_sha256='long',start=0,end=2,frames=60,safe_trim_ranges=[])]
        lengths={len(plan_by_duration(candidates,{'segments':[{'end':2}]},2,seed=i)['parts']) for i in range(40)}
        self.assertEqual(lengths,{1,2})

    def test_duration_prefers_fresh_ending_and_allows_feasible_fallback(self):
        candidates=self.candidates()
        counts={c['asset_sha256']:1 for c in candidates[:-1]}
        for pool,expected in [(candidates,'005'),(candidates[:1],'001')]:
            for seed in range(10):
                plan=plan_by_duration(pool,{'segments':[{'end':1}]},1,seed=seed,ending_counts=counts)
                self.assertEqual(plan['parts'][-1]['shot_id'],expected)

    def test_random_safe_start_frames_vary_without_crossing_action(self):
        candidates=[dict(id='safe',name='one.mp4',asset_sha256='safe',start=0,end=2,frames=60,safe_trim_ranges=[dict(start=0,end=2)])]
        starts={plan_by_duration(candidates,{'segments':[{'end':1}]},1,seed=i)['parts'][0]['start'] for i in range(30)}
        self.assertGreater(len(starts),3)
        self.assertTrue(all(0<=s<=1 for s in starts))

    def test_batch_compares_feasible_plans_without_losing_last_valid_choice(self):
        pool = self.candidates()
        timeline = {'segments': [{'end': 1}]}
        args = dict(seed=4, free_selection=True)
        first = plan_by_duration(pool, timeline, 1, **args)['parts']
        args['batch_history'] = [first]
        alternative = plan_by_duration(pool, timeline, 1, **args)['parts']
        self.assertNotEqual(first[0]['asset_sha256'], alternative[0]['asset_sha256'])
        # Three nodes allow the original valid plan but no additional search.
        limited = plan_by_duration(pool, timeline, 1, max_nodes=3, **args)
        self.assertEqual(limited['parts'], first)
