//! Exact ordered bit-pair dictionary; no arithmetic or rank averaging.
use super::*;
const DICT_CAP:usize=256;
const TABLE_CAP:usize=512;
const DICT_OVERHEAD:usize=128;
pub(super) struct MomentDictPlan{
    table:[u16;TABLE_CAP], values:[(f64,f64);DICT_CAP], len:usize, rows:usize,
}
fn bit_pair(x:(f64,f64))->(u64,u64){(x.0.to_bits(),x.1.to_bits())}
fn slot(x:(f64,f64))->usize{
    let(a,b)=bit_pair(x);
    let h=a.rotate_left(23)^b.wrapping_mul(0x9e3779b97f4a7c15);
    ((h^(h>>33)).wrapping_mul(0xff51afd7ed558ccd)>>(64-9))as usize
}
impl MomentDictPlan{
    pub(super) fn new()->Self{Self{table:[u16::MAX;TABLE_CAP],values:[(0.,0.);DICT_CAP],len:0,rows:0}}
    pub(super) fn add(&mut self,x:(f64,f64))->bool{
        let mut pos=slot(x);
        for _ in 0..TABLE_CAP{
            let id=self.table[pos];
            if id==u16::MAX{
                if self.len==DICT_CAP{return false}
                self.table[pos]=self.len as u16;self.values[self.len]=x;self.len+=1;self.rows+=1;return true
            }
            if bit_pair(self.values[id as usize])==bit_pair(x){self.rows+=1;return true}
            pos=(pos+1)&(TABLE_CAP-1);
        }
        false
    }
    pub(super) fn lookup(&self,x:(f64,f64))->Option<u8>{
        let mut pos=slot(x);
        for _ in 0..TABLE_CAP{
            let id=self.table[pos];
            if id==u16::MAX{return None}
            if bit_pair(self.values[id as usize])==bit_pair(x){return Some(id as u8)}
            pos=(pos+1)&(TABLE_CAP-1);
        }
        None
    }
    pub(super) fn bytes(&self)->usize{self.rows.saturating_add(self.len.saturating_mul(16)).saturating_add(DICT_OVERHEAD)}
    pub(super) fn worthwhile(&self)->bool{self.rows>=16&&self.bytes()<self.rows.saturating_mul(16)}
    pub(super) fn build(&self,rows:&[(f64,f64)])->CoreResult<MomentDict>{
        if rows.len()!=self.rows||!self.worthwhile(){return Err(val("moment dictionary plan shape/cost differs"))}
        let mut codes=checkpoint_vec(rows.len())?;let mut values=checkpoint_vec(self.len)?;
        if codes.capacity()!=rows.len()||values.capacity()!=self.len{return Err(budget("moment dictionary exact capacity differs"))}
        for &x in rows{codes.push(self.lookup(x).ok_or_else(||val("moment dictionary lookup differs"))?);}
        values.extend_from_slice(&self.values[..self.len]);
        Ok(MomentDict{codes:Arc::new(codes),values})
    }
}
pub(super) struct MomentDict{pub(super) codes:Arc<Vec<u8>>,pub(super) values:Vec<(f64,f64)>}
impl MomentDict{
    pub(super) fn len(&self)->usize{self.codes.len()}
    pub(super) fn bytes(&self)->usize{self.payload_bytes().saturating_add(DICT_OVERHEAD)}
    pub(super) fn payload_bytes(&self)->usize{self.codes.capacity().saturating_add(self.values.capacity().saturating_mul(16))}
    pub(super) fn iter(&self)->impl ExactSizeIterator<Item=&(f64,f64)>+Clone{
        self.codes.iter().map(|&i|&self.values[i as usize])
    }
    pub(super) fn get(&self,i:usize)->&(f64,f64){&self.values[self.codes[i]as usize]}
}
pub(super) fn plan(rows:&[(f64,f64)])->Option<MomentDictPlan>{
    if rows.len()<16{return None}
    let mut p=MomentDictPlan::new();
    for &x in rows{if !p.add(x){return None}}
    p.worthwhile().then_some(p)
}
#[cfg(test)]
mod tests{
    use super::*;
    #[test]
    fn bit_pair_dictionary_preserves_every_ordinal_and_signed_zero(){
        let xs:Vec<_>=(0..1025).map(|i|match i%4{0=>(0.125,-0.),1=>(0.125,0.),2=>(f64::from_bits(1),1.),_=>(0.25,2.)}).collect();
        let p=plan(&xs).expect("repeated bit pairs must admit dictionary");
        let d=p.build(&xs).unwrap();
        assert!(d.bytes()<16*xs.len());assert_eq!(d.len(),xs.len());
        assert_eq!(d.iter().map(|&x|bit_pair(x)).collect::<Vec<_>>(),xs.iter().map(|&x|bit_pair(x)).collect::<Vec<_>>());
        assert_ne!(d.codes[0],d.codes[1]);
        let unique:Vec<_>=(0..257).map(|i|(1.,i as f64)).collect();
        assert!(plan(&unique).is_none());
    }
}
